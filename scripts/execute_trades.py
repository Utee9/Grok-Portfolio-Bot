"""
Executes a list of sized trades via `bgc`, scoped to a specific portfolio's
Bitget sub-account credentials. Respects that portfolio's own dry_run /
paper_trading flags (from its status.json, see portfolio_config.py) --
each portfolio can be independently toggled between dry-run, paper
trading, and live.
"""

import os
import subprocess

from ticker_mapping import to_trading_pair
from size_positions import get_last_price, _bgc_env

def execute_trade(trade: dict, portfolio) -> dict:
    env = _bgc_env(portfolio)
    pair = to_trading_pair(trade["bitget_symbol"])

    command = [
        "bgc", "order", "--action", "place",
        "--category", "SPOT",
        "--symbol", pair,
        "--side", trade["side"],
        "--orderType", "market",
    ]

    if trade["side"] == "buy":
        # Market buy: qty is quote coin (USDT) -- matches usdt_amount directly
        command += ["--qty", str(trade["usdt_amount"])]
    else:
        # Market sell: qty must be base-coin (share/token count), so convert
        # using the live price.
        try:
            price = get_last_price(trade["bitget_symbol"], env)
        except RuntimeError as e:
            return {**trade, "status": "failed", "stderr": f"Price lookup failed: {e}"}
        qty = round(trade["usdt_amount"] / price, 6)
        command += ["--qty", str(qty)]

    if portfolio.paper_trading:
        command.append("--paper-trading")

    if portfolio.dry_run:
        return {**trade, "status": "dry_run_skipped", "command": " ".join(command)}

    result = subprocess.run(command, capture_output=True, text=True, env=env)

    return {
        **trade,
        "status": "executed" if result.returncode == 0 else "failed",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def execute_all(trades: list[dict], portfolio) -> list[dict]:
    return [execute_trade(trade, portfolio) for trade in trades]
