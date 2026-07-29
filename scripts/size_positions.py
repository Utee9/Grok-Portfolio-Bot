"""
Sizes trades by computing each position's TARGET dollar value from a
portfolio's stated weight % against your TOTAL portfolio value in that
portfolio's own Bitget sub-account (cash + current holdings) -- then buys
or sells the difference between that target and what you currently hold.

Each portfolio's `bgc` calls are authenticated using that portfolio's own
scoped API credentials (see portfolio_config.py for how the env var names
are resolved -- Grok uses unprefixed BITGET_* vars, others use suffixed
ones like BITGET_API_KEY_CLAUDE).
"""

import os
import subprocess
import json

MAX_SINGLE_TRADE_USDT = 50
MIN_TRADE_USDT = 5


def _bgc_env(portfolio) -> dict:
    """Builds the environment bgc needs, scoped to this portfolio's sub-account."""
    env = os.environ.copy()
    env["BITGET_API_KEY"] = portfolio.get_required_env("BITGET_API_KEY")
    env["BITGET_SECRET_KEY"] = portfolio.get_required_env("BITGET_SECRET_KEY")
    env["BITGET_PASSPHRASE"] = portfolio.get_required_env("BITGET_PASSPHRASE")
    return env


def get_account_snapshot(portfolio) -> dict:
    """
    Returns {"cash_usdt": float, "holdings_by_symbol": {...}, "total_value_usdt": float}
    for this portfolio's specific Bitget sub-account.

    NOTE: verify exact `bgc` command names/response shapes with `bgc discover`.
    """
    env = _bgc_env(portfolio)
    cash = _get_cash_balance(env)
    holdings = _get_holdings_value_by_symbol(env)
    total = cash + sum(holdings.values())
    return {"cash_usdt": cash, "holdings_by_symbol": holdings, "total_value_usdt": total}


def _run_bgc(args: list[str], env: dict) -> dict:
    result = subprocess.run(
        ["bgc", *args, "--pretty=false"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bgc {' '.join(args)} failed (exit {result.returncode})\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def _get_cash_balance(env: dict) -> float:
    data = _run_bgc(["account", "account_overview"], env)
    usdt_entry = next((a for a in data["data"] if a.get("coin") == "USDT"), None)
    if usdt_entry is None:
        raise RuntimeError("Could not find a USDT balance in account overview response")
    return float(usdt_entry["available"])


def _get_holdings_value_by_symbol(env: dict) -> dict:
    data = _run_bgc(["position", "all_position"], env)
    holdings = {}
    for pos in data.get("data", []):
        symbol = pos.get("symbol")
        value = float(pos.get("usdtValue", pos.get("marketValue", 0)) or 0)
        if symbol and value > 0:
            holdings[symbol] = value
    return holdings

def compute_rebalance_trades(
    target_weights: dict,
    ticker_map: dict,
    snapshot: dict,
    allow_closures: bool,
) -> list[dict]:
    total_value = snapshot["total_value_usdt"]
    holdings_by_symbol = snapshot["holdings_by_symbol"]

    symbol_to_ticker = {v: k for k, v in ticker_map.items() if v}
    held_value_by_ticker = {
        symbol_to_ticker[symbol]: value
        for symbol, value in holdings_by_symbol.items()
        if symbol in symbol_to_ticker
    }

    trades = []

    for ticker, weight_pct in target_weights.items():
        symbol = ticker_map.get(ticker)
        if not symbol:
            continue

        target_value = total_value * (weight_pct / 100)
        current_value = held_value_by_ticker.get(ticker, 0.0)
        delta = target_value - current_value

        if abs(delta) < MIN_TRADE_USDT:
            continue

        side = "buy" if delta > 0 else "sell"
        usdt_amount = round(min(abs(delta), MAX_SINGLE_TRADE_USDT), 2)

        trades.append({
            "ticker": ticker,
            "bitget_symbol": symbol,
            "side": side,
            "usdt_amount": usdt_amount,
            "reason": (
                f"rebalance to {weight_pct}% target "
                f"(held ${current_value:.2f}, target ${target_value:.2f})"
            ),
        })

    if allow_closures:
        for ticker, value in held_value_by_ticker.items():
            if ticker not in target_weights and value >= MIN_TRADE_USDT:
                symbol = ticker_map.get(ticker)
                if not symbol:
                    continue
                trades.append({
                    "ticker": ticker,
                    "bitget_symbol": symbol,
                    "side": "sell",
                    "usdt_amount": round(min(value, MAX_SINGLE_TRADE_USDT), 2),
                    "reason": f"closed: no longer in target weights (held ${value:.2f})",
                })

    return trades
