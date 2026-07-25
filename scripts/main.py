"""
Entry point for the Grok Portfolio mirror pipeline. Run by GitHub Actions
on a schedule (see .github/workflows/grok_mirror.yml), or manually with:

    python scripts/main.py
"""

import json
import datetime
from pathlib import Path

from fetch_grok_portfolio import fetch_latest_positions
from diff_engine import load_latest_state, compute_diff, save_latest_state
from ticker_mapping import load_ticker_map, annotate_changes_with_symbols
from size_positions import get_account_balance_usdt, size_trades
from execute_trades import execute_all
from notify import send_telegram_message, build_run_summary

SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"

# If a new extraction has fewer positions than this fraction of the previous
# book, treat it as a partial tweet (not a full portfolio disclosure) and
# suppress "closed" position changes -- otherwise a partial update makes
# untouched positions look like they were sold off.
PARTIAL_BOOK_THRESHOLD = 0.7


def save_snapshot(current: dict) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    snapshot_path = SNAPSHOTS_DIR / f"{timestamp}.json"
    snapshot_path.write_text(json.dumps(current, indent=2))


def is_partial_book(previous_count: int, current_count: int) -> bool:
    if previous_count == 0:
        return False  # first-ever run, nothing to compare against
    return current_count < previous_count * PARTIAL_BOOK_THRESHOLD


def main() -> None:
    previous_state = load_latest_state()

    print("[main] Fetching latest Grok portfolio data...")
    current_extraction = fetch_latest_positions()

    current_state = {
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "positions": current_extraction.get("positions", []),
        "source_posts": current_extraction.get("source_posts", []),
        "notes": current_extraction.get("notes", ""),
    }

    save_snapshot(current_state)

    changes = compute_diff(previous_state, current_state)

    partial = is_partial_book(
        len(previous_state.get("positions", [])),
        len(current_state.get("positions", [])),
    )
    if partial:
        print(
            "[main] New extraction looks like a partial update "
            f"({len(current_state['positions'])} positions vs "
            f"{len(previous_state['positions'])} previously). "
            "Suppressing 'closed' position changes this run."
        )
        changes = [c for c in changes if c["action"] != "closed"]

    if not changes:
        print("[main] No actionable changes detected.")
        send_telegram_message(build_run_summary([], []))
        save_latest_state(current_state)
        return

    ticker_map = load_ticker_map()
    tradeable, unmapped = annotate_changes_with_symbols(changes, ticker_map)

    if unmapped:
        print(f"[main] {len(unmapped)} ticker(s) have no Bitget mapping: "
              f"{[u['ticker'] for u in unmapped]}")

    execution_results = []
    if tradeable:
        balance = get_account_balance_usdt()
        print(f"[main] Sub-account balance: {balance} USDT")

        trades = size_trades(tradeable, balance)
        print(f"[main] Sizing produced {len(trades)} trade(s) after min/max filters.")

        execution_results = execute_all(trades)

    summary = build_run_summary(execution_results, unmapped)
    print(summary)
    send_telegram_message(summary)

    # Only persist as "latest" once we've acted on it -- keeps latest.json
    # and the executed trades in sync with each other.
    save_latest_state(current_state)


if __name__ == "__main__":
    main()
