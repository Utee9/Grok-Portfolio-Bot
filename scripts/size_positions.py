"""
Turns a "weight went from X% to Y%" change into an actual USDT amount to
buy or sell, sized against your current sub-account balance (not Grok's
$50K account -- yours is almost certainly a different size).
"""

import subprocess
import json

# Safety rails -- tune these to your own risk tolerance before going live.
MAX_SINGLE_TRADE_USDT = 50       # hard ceiling per single order while testing
MIN_TRADE_USDT = 5               # skip trades smaller than this (not worth the fee)


def get_account_balance_usdt() -> float:
    """
    Shells out to the Bitget Agent CLI to fetch the current USDT balance
    of whichever account/sub-account the configured API key belongs to.
    Verify the exact `bgc` command/output shape with `bgc discover` --
    this assumes an `account account_overview` style command returning JSON.
    """
    result = subprocess.run(
        ["bgc", "account", "account_overview", "--pretty=false"],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    # NOTE: adjust this path once you've confirmed the real response shape
    usdt_entry = next(
        (a for a in data["data"] if a.get("coin") == "USDT"), None
    )
    if usdt_entry is None:
        raise RuntimeError("Could not find a USDT balance in account overview response")
    return float(usdt_entry["available"])


def size_trades(tradeable_changes: list[dict], account_balance_usdt: float) -> list[dict]:
    """
    Given change events (with weight_pct deltas) and total account balance,
    returns concrete trade instructions: side (buy/sell) and USDT amount.
    """
    trades = []

    for change in tradeable_changes:
        action = change["action"]

        if action == "new":
            target_pct = change["to_pct"]
            delta_pct = target_pct
            side = "buy"
        elif action == "increase":
            delta_pct = change["to_pct"] - change["from_pct"]
            side = "buy"
        elif action == "decrease":
            delta_pct = change["from_pct"] - change["to_pct"]
            side = "sell"
        elif action == "closed":
            # Handled separately by main.py -- closures need extra
            # confirmation since a partial tweet extraction can make an
            # untouched position look "closed" by omission.
            continue
        else:
            continue

        usdt_amount = round(account_balance_usdt * (delta_pct / 100), 2)

        if usdt_amount < MIN_TRADE_USDT:
            continue  # too small to bother with -- avoids fee-eaten dust trades

        usdt_amount = min(usdt_amount, MAX_SINGLE_TRADE_USDT)

        trades.append({
            "ticker": change["ticker"],
            "bitget_symbol": change["bitget_symbol"],
            "side": side,
            "usdt_amount": usdt_amount,
            "reason": f"{action}: {change.get('from_pct', 0)}% -> {change.get('to_pct')}%",
        })

    return trades
