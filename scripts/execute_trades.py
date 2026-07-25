"""
Executes a list of sized trades via `bgc`. Respects DRY_RUN so you can
rehearse the full pipeline (fetch -> diff -> size -> "execute") without
ever placing a real order, and separately respects Bitget's own
--paper-trading demo-account mode if you want a step above dry-run that
still hits a real (sandboxed) order book.
"""

import os
import subprocess


def execute_trade(trade: dict, dry_run: bool, paper_trading: bool) -> dict:
    """
    Places a single market order for `trade` via bgc. Returns a result dict
    for logging/notification purposes.
    """
    verb = "order market_buy" if trade["side"] == "buy" else "order market_sell"

    command = [
        "bgc", *verb.split(),
        "--symbol", trade["bitget_symbol"],
        "--quote-amount", str(trade["usdt_amount"]),
    ]
    if paper_trading:
        command.append("--paper-trading")

    if dry_run:
        return {
            **trade,
            "status": "dry_run_skipped",
            "command": " ".join(command),
        }

    result = subprocess.run(command, capture_output=True, text=True)

    return {
        **trade,
        "status": "executed" if result.returncode == 0 else "failed",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def execute_all(trades: list[dict]) -> list[dict]:
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    paper_trading = os.environ.get("PAPER_TRADING", "false").lower() == "true"

    results = []
    for trade in trades:
        results.append(execute_trade(trade, dry_run=dry_run, paper_trading=paper_trading))
    return results
