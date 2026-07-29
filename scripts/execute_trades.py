"""
Executes a list of sized trades via `bgc`, scoped to a specific portfolio's
Bitget sub-account credentials. Respects that portfolio's own dry_run /
paper_trading flags (from its status.json, see portfolio_config.py) --
each portfolio can be independently toggled between dry-run, paper
trading, and live.
"""

import os
import subprocess


def _bgc_env(portfolio) -> dict:
    env = os.environ.copy()
    env["BITGET_API_KEY"] = portfolio.get_required_env("BITGET_API_KEY")
    env["BITGET_SECRET_KEY"] = portfolio.get_required_env("BITGET_SECRET_KEY")
    env["BITGET_PASSPHRASE"] = portfolio.get_required_env("BITGET_PASSPHRASE")
    return env


def execute_trade(trade: dict, portfolio) -> dict:
    verb = "order market_buy" if trade["side"] == "buy" else "order market_sell"

    command = [
        "bgc", *verb.split(),
        "--symbol", trade["bitget_symbol"],
        "--quote-amount", str(trade["usdt_amount"]),
    ]
    if portfolio.paper_trading:
        command.append("--paper-trading")

    if portfolio.dry_run:
        return {**trade, "status": "dry_run_skipped", "command": " ".join(command)}

    result = subprocess.run(command, capture_output=True, text=True, env=_bgc_env(portfolio))

    return {
        **trade,
        "status": "executed" if result.returncode == 0 else "failed",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def execute_all(trades: list[dict], portfolio) -> list[dict]:
    return [execute_trade(trade, portfolio) for trade in trades]
