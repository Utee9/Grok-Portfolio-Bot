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


def _run_bgc(args: list[str], env: dict) -> dict:
    result = subprocess.run(
        ["bgc", *args],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bgc {' '.join(args)} failed (exit {result.returncode})\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return json.loads(result.stdout)

def get_account_snapshot(portfolio) -> dict:
    env = _bgc_env(portfolio)
    response = _run_bgc(["account_overview"], env)
    assets_section = response.get("data", {}).get("assets", {})

    if not assets_section.get("ok"):
        raise RuntimeError(f"account_overview 'assets' section failed: {assets_section.get('error')}")

    cash = 0.0
    holdings = {}  # keyed by UPPERCASED coin symbol, for case-insensitive matching downstream
    for entry in assets_section["data"].get("assets", []):
        coin = entry.get("coin")
        if not coin:
            continue
        if coin.upper() == "USDT":
            cash = float(entry.get("available", 0) or 0)
        else:
            value = float(entry.get("usdValue", 0) or 0)
            if value > 0:
                holdings[coin.upper()] = value

    total = cash + sum(holdings.values())
    return {"cash_usdt": cash, "holdings_by_symbol": holdings, "total_value_usdt": total}


def get_last_price(bitget_symbol: str, env: dict) -> float:
    """Live last-traded price for a tokenized-stock pair, e.g. rMU -> rMUUSDT."""
    from ticker_mapping import to_trading_pair
    pair = to_trading_pair(bitget_symbol)
    result = _run_bgc(["market", "--action", "tickers", "--category", "SPOT", "--symbol", pair], env)
    data = result.get("data", [])
    if not data:
        raise RuntimeError(f"No ticker data returned for {pair}")
    return float(data[0]["lastPrice"])


def compute_rebalance_trades(target_weights, ticker_map, snapshot, allow_closures) -> list[dict]:
    total_value = snapshot["total_value_usdt"]
    holdings_by_symbol = snapshot["holdings_by_symbol"]  # keys are UPPERCASE coin symbols

    symbol_to_ticker = {v.upper(): k for k, v in ticker_map.items() if v}
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
            "reason": f"target ${target_value:.2f} vs held ${current_value:.2f}",
        })

    if allow_closures:
        for ticker, value in held_value_by_ticker.items():
            if ticker in target_weights or value < MIN_TRADE_USDT:
                continue
            symbol = ticker_map.get(ticker)
            if not symbol:
                continue
            trades.append({
                "ticker": ticker,
                "bitget_symbol": symbol,
                "side": "sell",
                "usdt_amount": round(min(value, MAX_SINGLE_TRADE_USDT), 2),
            })

    return trades
