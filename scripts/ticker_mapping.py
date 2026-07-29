import json
from pathlib import Path


def load_ticker_map(ticker_map_path: Path) -> dict:
    raw = json.loads(ticker_map_path.read_text())
    # Strip documentation/comment keys before use
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def resolve_symbol(ticker: str, ticker_map: dict) -> str | None:
    return ticker_map.get(ticker)
