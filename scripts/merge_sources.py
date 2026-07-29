"""
Reconciles two input sources into one set of target weights:

1. Tweet-based extraction (from fetch_tweets.py) -- updates automatically
   for portfolios with a live X account, but coverage depends on what gets
   posted and how well it can be extracted.
2. A manually-edited JSON file (each portfolio's
   config/manual_override.json) -- precise since you're reading it
   straight off the app, but only as fresh as your last edit.

Rather than picking one source over the other wholesale, this merges them
PER TICKER based on which one has a more recent "as_of" date for that
specific ticker. This means partial/irregular manual updates are safe --
they only override tickers you've actually looked at recently.
"""

import json
import datetime
from pathlib import Path


def _parse_date(value: str) -> datetime.date:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def load_merged_state(merged_state_path: Path) -> dict:
    if not merged_state_path.exists():
        return {}

    raw = json.loads(merged_state_path.read_text())
    return {
        ticker: {
            "weight_pct": entry["weight_pct"],
            "as_of": _parse_date(entry["as_of"]),
            "source": entry["source"],
        }
        for ticker, entry in raw.items()
    }


def save_merged_state(merged_state_path: Path, state: dict) -> None:
    merged_state_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        ticker: {
            "weight_pct": entry["weight_pct"],
            "as_of": entry["as_of"].isoformat(),
            "source": entry["source"],
        }
        for ticker, entry in state.items()
    }
    merged_state_path.write_text(json.dumps(serializable, indent=2))


def merge_source_into_state(
    state: dict,
    positions: list[dict],
    as_of: datetime.date,
    source: str,
) -> dict:
    updated = dict(state)

    for position in positions:
        ticker = position["ticker"]
        existing = updated.get(ticker)

        if existing is None or as_of >= existing["as_of"]:
            updated[ticker] = {
                "weight_pct": position["weight_pct"],
                "as_of": as_of,
                "source": source,
            }

    return updated


def load_manual_override(path: Path) -> tuple[list[dict], datetime.date] | None:
    if not path.exists():
        return None

    raw = json.loads(path.read_text())
    if not raw.get("as_of") or not raw.get("positions"):
        return None

    return raw["positions"], _parse_date(raw["as_of"])


def build_target_weights(state: dict) -> dict:
    return {ticker: entry["weight_pct"] for ticker, entry in state.items()}
