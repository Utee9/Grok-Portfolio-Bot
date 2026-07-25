"""
Diffs a new portfolio extraction against the last saved snapshot to figure
out what actually changed -- new positions, closed positions, and weight
changes on existing ones.
"""

import json
from pathlib import Path

LATEST_PATH = Path(__file__).parent.parent / "data" / "latest.json"

# Ignore weight changes smaller than this -- avoids reacting to noise/rounding
# differences between successive tweet extractions of the same position.
MIN_WEIGHT_CHANGE_PCT = 0.5


def load_latest_state() -> dict:
    if not LATEST_PATH.exists():
        return {"fetched_at": None, "positions": []}
    return json.loads(LATEST_PATH.read_text())


def positions_by_ticker(positions: list[dict]) -> dict:
    return {p["ticker"]: p for p in positions}


def compute_diff(previous: dict, current: dict) -> list[dict]:
    """
    Returns a list of change events, e.g.:
      {"ticker": "NOW", "action": "increase", "from_pct": 10.0, "to_pct": 12.6}
      {"ticker": "ZETA", "action": "new", "to_pct": 9.5}
      {"ticker": "AVGO", "action": "closed", "from_pct": 6.0}
    """
    prev_positions = positions_by_ticker(previous.get("positions", []))
    curr_positions = positions_by_ticker(current.get("positions", []))

    changes = []

    # New or changed positions
    for ticker, curr in curr_positions.items():
        prev = prev_positions.get(ticker)
        if prev is None:
            changes.append({
                "ticker": ticker,
                "action": "new",
                "to_pct": curr["weight_pct"],
            })
        else:
            delta = curr["weight_pct"] - prev["weight_pct"]
            if abs(delta) >= MIN_WEIGHT_CHANGE_PCT:
                changes.append({
                    "ticker": ticker,
                    "action": "increase" if delta > 0 else "decrease",
                    "from_pct": prev["weight_pct"],
                    "to_pct": curr["weight_pct"],
                })

    # Positions that disappeared entirely (only trust this if the new
    # extraction looks like a *full* book -- see note in main.py)
    for ticker, prev in prev_positions.items():
        if ticker not in curr_positions:
            changes.append({
                "ticker": ticker,
                "action": "closed",
                "from_pct": prev["weight_pct"],
            })

    return changes


def save_latest_state(current: dict) -> None:
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(current, indent=2))
