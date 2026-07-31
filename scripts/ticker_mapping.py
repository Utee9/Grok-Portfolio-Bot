from size_positions import _run_bgc


def load_ticker_map(ticker_map_path) -> dict:
    import json
    raw = json.loads(ticker_map_path.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_cash_proxies(ticker_map_path) -> set:
    import json
    raw = json.loads(ticker_map_path.read_text())
    proxies = raw.get("_cash_proxies", {})
    return {ticker for ticker, mode in proxies.items() if mode == "HOLD_AS_USDT"}


def resolve_symbol(ticker: str, ticker_map: dict) -> str | None:
    return ticker_map.get(ticker)


def to_trading_pair(base_symbol: str) -> str:
    """rMU -> rMUUSDT. All Bitget TradFi tokenized-stock pairs quote in USDT."""
    return f"{base_symbol}USDT"


def suggest_mapping(ticker: str, env: dict) -> str | None:
    """
    Checks whether Bitget lists a tokenized-stock spot pair for this ticker
    using the confirmed 'r' prefix convention (e.g. MU -> rMU, traded as
    rMUUSDT). Returns the BASE symbol (e.g. "rMU") if found live on
    Bitget, else None. Read-only -- does not write to ticker_map.json.
    """
    candidate_base = f"r{ticker}"
    pair = to_trading_pair(candidate_base)
    try:
        result = _run_bgc(["market", "--action", "tickers", "--category", "SPOT", "--symbol", pair], env)
    except RuntimeError:
        return None  # bgc raised (e.g. process-level failure) -- treat as not found
    data = result.get("data", [])
    return candidate_base if data else None

def load_unavailable(ticker_map_path) -> set:
    import json
    raw = json.loads(ticker_map_path.read_text())
    return set(raw.get("_unavailable_on_bitget", {}).keys())
