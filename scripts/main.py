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
from ticker_mapping import load_ticker_map
from size_positions import get_account_snapshot, compute_rebalance_trades
from execute_trades import execute_all
from notify import send_telegram_message, build_run_summary

SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"

# If a new extraction has fewer positions than this fraction of the previous
# book, treat it as a partial tweet (not a full portfolio disclosure) --
# suppress closing any position not mentioned in it, since a partial post
# would otherwise make untouched positions look like they were dropped.
PARTIAL_BOOK_THRESHOLD = 0.7


def save_snapshot(current: dict) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    snapshot_path = SNAPSHOTS_DIR / f"{timestamp}.json"
    snapshot_path.write_text(json.dumps(current, indent=2))


def is_partial_book(previous_count: int, current_count: int) -> bool:
    if previous_count == 0:
        return False  # first-ever run -- nothing to compare against, and
                       # we WANT the full initial buy to go through
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

    # Kept for the run summary / visibility into what changed, even though
    # trade sizing itself now works off absolute target weights rather than
    # these deltas directly.
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
            "Closures will be suppressed this run."
        )

    if not current_state["positions"]:
        print("[main] No positions extracted this run -- nothing to do.")
        send_telegram_message(build_run_summary([], [], changes))
        return

    target_weights = {p["ticker"]: p["weight_pct"] for p in current_state["positions"]}
    ticker_map = load_ticker_map()

    unmapped = [
        {"ticker": t, "action": "unmapped"}
        for t in target_weights
        if not ticker_map.get(t)
    ]
    if unmapped:
        print(f"[main] {len(unmapped)} ticker(s) have no Bitget mapping: "
              f"{[u['ticker'] for u in unmapped]}")

    print("[main] Fetching current sub-account snapshot (cash + holdings)...")
    snapshot = get_account_snapshot()
    print(f"[main] Total portfolio value: {snapshot['total_value_usdt']} USDT "
          f"(cash: {snapshot['cash_usdt']} USDT)")

    trades = compute_rebalance_trades(
        target_weights=target_weights,
        ticker_map=ticker_map,
        snapshot=snapshot,
        allow_closures=not partial,
    )
    print(f"[main] Rebalancing produced {len(trades)} trade(s) after min/max filters.")

    execution_results = execute_all(trades)

    summary = build_run_summary(execution_results, unmapped, changes)
    print(summary)
    send_telegram_message(summary)

    save_latest_state(current_state)


if __name__ == "__main__":
    main()
