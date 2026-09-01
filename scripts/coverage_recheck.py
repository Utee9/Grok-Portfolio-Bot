"""
Periodic MEXC-exclusivity check -- NOT part of the trading pipeline.
Run this on a low-frequency schedule (weekly/monthly), separate from
the 6-hour mirror.yml trading workflow. Purely informational: never
places trades, never touches sub-accounts.

Scope note: this used to also re-check ticker_map.json against live
Bitget data, but that job is now redundant -- generate_mapping_suggestions.py
+ suggest-ticker-mappings.yml already does that daily, via a reviewable
PR, better than this script did. So this script trusts config/ticker_map.json
as the current source of truth for Bitget coverage and focuses on its one
remaining unique job: has MEXC's Ondo catalog ever grown a ticker that
Bitget's Reality tokens don't have? As of the last full manual check,
MEXC was a strict subset of Bitget (zero unique tickers) -- this is the
automated version of re-checking that periodically.
"""

import json
import urllib.request

from portfolio_config import PortfolioConfig, PORTFOLIOS_ROOT
from merge_sources import load_merged_state, build_target_weights
from ticker_mapping import load_ticker_map, load_cash_proxies
from notify import send_telegram_message

ALL_PORTFOLIOS = [d.name for d in PORTFOLIOS_ROOT.iterdir() if d.is_dir()]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def get_current_ground_truth_tickers() -> set:
    """Every ticker any portfolio currently holds a target weight for."""
    tickers = set()
    for name in ALL_PORTFOLIOS:
        portfolio = PortfolioConfig(name)
        merged_state = load_merged_state(portfolio.merged_state_path)
        target_weights = build_target_weights(merged_state)
        tickers.update(t.upper() for t in target_weights)
    return tickers


def get_bitget_covered_tickers(ticker_map_path) -> set:
    """
    Tickers currently confirmed mapped to a real Bitget symbol.
    Trusts config/ticker_map.json as current -- kept fresh by the
    existing daily suggest-ticker-mappings.yml workflow, no need to
    hit Bitget's API again here.
    """
    ticker_map = load_ticker_map(ticker_map_path)  # already excludes _-prefixed meta keys
    return {t.upper() for t, symbol in ticker_map.items() if symbol}


def fetch_mexc_ondo_tickers() -> set:
    url = "https://api.mexc.com/api/v3/exchangeInfo"
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    result = set()
    for s in data.get("symbols", []):
        base, quote = s.get("baseAsset", ""), s.get("quoteAsset", "")
        if quote == "USDT" and (base.endswith("ON") or base.endswith("ION")):
            underlying = base[:-3] if base.endswith("ION") else base[:-2]
            result.add(underlying.upper())
    return result


def main():
    ticker_map_path = PortfolioConfig(ALL_PORTFOLIOS[0]).ticker_map_path  # single shared file
    cash_proxies = load_cash_proxies(ticker_map_path)

    ground_truth = get_current_ground_truth_tickers() - cash_proxies
    bitget_covered = get_bitget_covered_tickers(ticker_map_path)

    lines = ["[Coverage recheck] MEXC-exclusivity check:\n"]
    lines.append(f"Current live ticker set across all portfolios: {len(ground_truth)} tickers")
    lines.append(f"Currently Bitget-mapped (per config/ticker_map.json): {len(bitget_covered)} tickers")

    try:
        mexc = fetch_mexc_ondo_tickers()
        lines.append(f"MEXC Ondo catalog: {len(mexc)} symbols live\n")

        mexc_exclusive = (ground_truth & mexc) - bitget_covered
        if mexc_exclusive:
            lines.append(
                f"!!! MEXC now covers ticker(s) Bitget does NOT: {sorted(mexc_exclusive)} "
                f"-- worth reconsidering the MEXC integration sketch."
            )
        else:
            lines.append(
                "MEXC still adds zero unique coverage beyond Bitget -- "
                "no reason to activate the MEXC integration yet."
            )
    except Exception as e:
        lines.append(f"MEXC fetch FAILED: {e}")

    summary = "\n".join(lines)
    print(summary)
    send_telegram_message(summary)


if __name__ == "__main__":
    main()
