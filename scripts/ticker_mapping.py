import json
from pathlib import Path


def load_ticker_map(ticker_map_path: Path) -> dict:
    raw = json.loads(ticker_map_path.read_text())
    # Strip documentation/comment keys before use
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_cash_proxies(ticker_map_path: Path) -> set[str]:
    """
    Tickers explicitly marked in ticker_map.json's `_cash_proxies` block as
    "HOLD_AS_USDT" -- e.g. T-bill ETFs like SGOV that Bitget doesn't
    tokenize. These are intentionally left untraded (their target weight
    just stays as idle USDT) rather than flagged as a missing/broken
    mapping.
    """
    raw = json.loads(ticker_map_path.read_text())
    proxies = raw.get("_cash_proxies", {})
    return {ticker for ticker, mode in proxies.items() if mode == "HOLD_AS_USDT"}


def resolve_symbol(ticker: str, ticker_map: dict) -> str | None:
    return ticker_map.get(ticker)
