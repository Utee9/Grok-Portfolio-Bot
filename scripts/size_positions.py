"""
Sizes trades by computing each position's TARGET dollar value from Grok's
stated weight % against your TOTAL portfolio value (cash + the current
market value of everything you already hold) -- then buys or sells the
difference between that target and what you currently hold.

This mirrors how the real Grok Portfolio actually operates: it's a fixed
starting pool of capital that gets fully reallocated each cycle (selling
down what should shrink, buying up what should grow), not a strategy that
just invests whatever spare cash happens to be sitting around.

A useful side effect of sizing it this way: on your very first real run,
you'll be holding nothing, so the "difference" for every target position
is simply its full target value -- meaning this naturally buys the entire
current 15-position book on day one, with no separate script needed.
"""

import subprocess
import json

# Safety rails -- tune these to your own risk tolerance before going live.
MAX_SINGLE_TRADE_USDT = 50       # hard ceiling per single order while testing
MIN_TRADE_USDT = 5               # skip trades smaller than this (not worth the fee)


def get_account_snapshot() -> dict:
    """
    Returns {"cash_usdt": float, "holdings_by_symbol": {"NOWx": value_usdt, ...},
    "total_value_usdt": float} by querying the sub-account via bgc.

    NOTE: verify the exact `bgc` command names and response shapes with
    `bgc discover` -- this assumes something like `bgc account
    account_overview` for cash and `bgc position all_position` (or similar)
    for currently-held tokenized stocks, each returning JSON with the
    fields referenced below. Adjust the field names once confirmed.
    """
    cash = _get_cash_balance()
    holdings = _get_holdings_value_by_symbol()
    total = cash + sum(holdings.values())
    return {
        "cash_usdt": cash,
        "holdings_by_symbol": holdings,
        "total_value_usdt": total,
    }


def _get_cash_balance() -> float:
    result = subprocess.run(
        ["bgc", "account", "account_overview", "--pretty=false"],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    usdt_entry = next(
        (a for a in data["data"] if a.get("coin") == "USDT"), None
    )
    if usdt_entry is None:
        raise RuntimeError("Could not find a USDT balance in account overview response")
    return float(usdt_entry["available"])


def _get_holdings_value_by_symbol() -> dict:
    """
    Returns {"NOWx": 62.30, "ZETAx": 47.10, ...} -- current USDT market
    value of each tokenized-stock position actually held right now.
    """
    result = subprocess.run(
        ["bgc", "position", "all_position", "--pretty=false"],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)

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
    """
    target_weights: {"NOW": 12.6, "ZETA": 9.5, ...} -- ticker -> weight %,
    taken directly from Grok's latest disclosed positions.

    allow_closures: if False, positions you currently hold that are NOT in
    target_weights are left alone rather than sold. Set this False when the
    latest extraction looks like a partial tweet (see main.py) -- otherwise
    an incomplete post could make the bot sell things Grok still holds but
    simply didn't mention in that particular update.

    Returns trade instructions: [{"ticker", "bitget_symbol", "side",
    "usdt_amount", "reason"}, ...]
    """
    total_value = snapshot["total_value_usdt"]
    holdings_by_symbol = snapshot["holdings_by_symbol"]

    symbol_to_ticker = {v: k for k, v in ticker_map.items() if v}
    held_value_by_ticker = {
        symbol_to_ticker[symbol]: value
        for symbol, value in holdings_by_symbol.items()
        if symbol in symbol_to_ticker
    }

    trades = []

    # Bring each target position to its target dollar value
    for ticker, weight_pct in target_weights.items():
        symbol = ticker_map.get(ticker)
        if not symbol:
            continue  # unmapped tickers are reported separately by the caller

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

    # Fully close anything we hold that's no longer in Grok's target list --
    # only when we trust this extraction to be a complete picture.
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
                    "reason": f"closed: no longer in Grok's target weights (held ${value:.2f})",
                })

    return trades
