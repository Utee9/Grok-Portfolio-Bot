import json
from pathlib import Path

TICKER_MAP_PATH = Path(__file__).parent.parent / "config" / "ticker_map.json"


def load_ticker_map() -> dict:
    raw = json.loads(TICKER_MAP_PATH.read_text())
    # Strip the documentation/comment keys before use
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def resolve_symbol(ticker: str, ticker_map: dict) -> str | None:
    """
    Returns the Bitget symbol for a ticker, or None if it's unmapped or
    explicitly marked as untradeable (e.g. a cash-equivalent ETF).
    """
    return ticker_map.get(ticker)
