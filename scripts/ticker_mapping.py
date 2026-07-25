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


def annotate_changes_with_symbols(changes: list[dict], ticker_map: dict) -> tuple[list[dict], list[dict]]:
    """
    Splits changes into (tradeable, unmapped) based on whether we have a
    Bitget symbol for the ticker. Unmapped changes should be logged/alerted,
    not silently dropped.
    """
    tradeable, unmapped = [], []
    for change in changes:
        symbol = resolve_symbol(change["ticker"], ticker_map)
        if symbol:
            change["bitget_symbol"] = symbol
            tradeable.append(change)
        else:
            unmapped.append(change)
    return tradeable, unmapped
