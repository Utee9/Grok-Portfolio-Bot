"""
Entry point for the portfolio-mirror pipeline. Runs for exactly ONE
portfolio per invocation, selected via the PORTFOLIO environment variable
(e.g. "grok", "claude", "deepseek", "gpt") -- see .github/workflows/
mirror.yml for how each portfolio gets its own scheduled run.

Manual run for a specific portfolio:

    PORTFOLIO=grok python scripts/main.py
"""

import os
import json
import datetime
from pathlib import Path

from portfolio_config import PortfolioConfig
from fetch_tweets import fetch_latest_positions
from merge_sources import (
    load_merged_state, save_merged_state, merge_source_into_state,
    load_manual_override, build_target_weights,
)
from ticker_mapping import load_ticker_map, load_cash_proxies
from size_positions import get_account_snapshot, compute_rebalance_trades
from execute_trades import execute_all
from notify import send_telegram_message, build_run_summary

PARTIAL_BOOK_THRESHOLD = 0.7


def save_snapshot(portfolio: PortfolioConfig, payload: dict) -> None:
    portfolio.snapshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    (portfolio.snapshots_dir / f"{timestamp}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )


def is_partial_book(previous_count: int, current_count: int) -> bool:
    if previous_count == 0:
        return False
    return current_count < previous_count * PARTIAL_BOOK_THRESHOLD


def main() -> None:
    portfolio_name = os.environ.get("PORTFOLIO")
    if not portfolio_name:
        raise RuntimeError(
            "PORTFOLIO environment variable not set. "
            "Expected one of: grok, claude, deepseek, gpt."
        )

    portfolio = PortfolioConfig(portfolio_name)
    print(f"[main] Running pipeline for: {portfolio.display_name} "
          f"(dry_run={portfolio.dry_run}, paper_trading={portfolio.paper_trading})")

    merged_state = load_merged_state(portfolio.merged_state_path)
    previous_ticker_count = len(merged_state)

    if portfolio.x_handle:
        print(f"[main] Fetching latest tweet-based extraction for @{portfolio.x_handle}...")
    else:
        print("[main] No X handle configured for this portfolio -- manual-only mode.")
    extraction = fetch_latest_positions(portfolio.x_handle)
    tweet_positions = extraction.get("positions", [])
    narrative_actions = extraction.get("narrative_actions", [])

    today = datetime.date.today()
    if tweet_positions:
        merged_state = merge_source_into_state(merged_state, tweet_positions, today, source="twitter")

    manual = load_manual_override(portfolio.manual_override_path)
    if manual:
        manual_positions, manual_as_of = manual
        print(f"[main] Merging manual override (as_of {manual_as_of})...")
        merged_state = merge_source_into_state(merged_state, manual_positions, manual_as_of, source="manual")

    save_snapshot(portfolio, {
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "tweet_extraction": extraction,
        "manual_override_used": manual is not None,
        "merged_state": merged_state,
    })

    partial = is_partial_book(previous_ticker_count, len(merged_state))
    if partial:
        print(
            f"[main] Merged target list looks partial ({len(merged_state)} "
            f"tickers vs {previous_ticker_count} previously). Closures suppressed this run."
        )

    if narrative_actions:
        print(f"[main] {len(narrative_actions)} narrative action(s) mentioned with no "
              f"weight -- alerting only, not auto-trading these.")

    target_weights = build_target_weights(merged_state)

    if not target_weights:
        print("[main] No target weights known yet -- nothing to do.")
        send_telegram_message(build_run_summary(portfolio.display_name, {}, [], [], narrative_actions))
        return

    ticker_map = load_ticker_map(portfolio.ticker_map_path)
    cash_proxies = load_cash_proxies(portfolio.ticker_map_path)

    unmapped = [
        t for t in target_weights
        if not ticker_map.get(t) and t not in cash_proxies
    ]
    if unmapped:
        print(f"[main] {len(unmapped)} ticker(s) have no Bitget mapping: {unmapped}")

    held_as_cash = [t for t in target_weights if t in cash_proxies]
    if held_as_cash:
        print(f"[main] {len(held_as_cash)} ticker(s) treated as cash-equivalent, "
              f"held as idle USDT (not traded): {held_as_cash}")

    if not portfolio.has_bitget_credentials():
        print(
            f"[main] No Bitget credentials configured for '{portfolio.name}' yet -- "
            f"tracking-only mode. Target weights recorded, no trades computed or placed."
        )
        summary = build_run_summary(
            portfolio.display_name, target_weights, [], unmapped,
            narrative_actions, tracking_only=True,
        )
        print(summary)
        send_telegram_message(summary)
        save_merged_state(portfolio.merged_state_path, merged_state)
        return

    print("[main] Fetching current sub-account snapshot (cash + holdings)...")
    snapshot = get_account_snapshot(portfolio)
    print(f"[main] Total portfolio value: {snapshot['total_value_usdt']} USDT "
          f"(cash: {snapshot['cash_usdt']} USDT)")

    trades = compute_rebalance_trades(
        target_weights=target_weights,
        ticker_map=ticker_map,
        snapshot=snapshot,
        allow_closures=not partial,
    )
    print(f"[main] Rebalancing produced {len(trades)} trade(s) after min/max filters.")

    execution_results = execute_all(trades, portfolio)

    summary = build_run_summary(portfolio.display_name, target_weights, execution_results, unmapped, narrative_actions)
    print(summary)
    send_telegram_message(summary)

    save_merged_state(portfolio.merged_state_path, merged_state)


if __name__ == "__main__":
    main()
