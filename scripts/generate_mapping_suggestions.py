"""
Standalone script: scans EVERY portfolio's target-weight tickers for any
that are unmapped or previously confirmed unavailable in the single
shared config/ticker_map.json, re-checks them against Bitget's live SPOT
ticker list (public data, no credentials needed), and writes any finds
back into that shared file on the current branch.

Runs once for the whole repo, not per-portfolio -- the mapping is shared
now, so a per-portfolio matrix would race writing to the same file.
"""
import json
import os

from portfolio_config import PortfolioConfig, PORTFOLIOS_ROOT
from merge_sources import load_merged_state, build_target_weights
from ticker_mapping import load_ticker_map, load_cash_proxies, load_unavailable, suggest_mapping


ALL_PORTFOLIOS = [d.name for d in PORTFOLIOS_ROOT.iterdir() if d.is_dir()]


def main():
    ticker_map_path = PortfolioConfig(ALL_PORTFOLIOS[0]).ticker_map_path  # same path for every portfolio now

    ticker_map = load_ticker_map(ticker_map_path)
    cash_proxies = load_cash_proxies(ticker_map_path)
    unavailable = load_unavailable(ticker_map_path)

    to_check = set()
    for name in ALL_PORTFOLIOS:
        portfolio = PortfolioConfig(name)
        merged_state = load_merged_state(portfolio.merged_state_path)
        target_weights = build_target_weights(merged_state)
        for ticker in target_weights:
            if ticker in cash_proxies:
                continue
            if not ticker_map.get(ticker) or ticker in unavailable:
                to_check.add(ticker)

    if not to_check:
        print("[suggest] Nothing to check -- all tickers across all portfolios already resolved.")
        return

    env = os.environ.copy()  # public market data -- no BITGET_* credentials needed
    found = {}
    for ticker in sorted(to_check):
        suggestion = suggest_mapping(ticker, env)
        if suggestion:
            found[ticker] = suggestion
            print(f"[suggest] {ticker} -> {suggestion}")
        else:
            print(f"[suggest] {ticker}: still not available on Bitget")

    if not found:
        print("[suggest] No new matches found.")
        return

    raw = json.loads(ticker_map_path.read_text())
    raw.update(found)
    unavailable_block = raw.get("_unavailable_on_bitget", {})
    for ticker in found:
        unavailable_block.pop(ticker, None)
    raw["_unavailable_on_bitget"] = unavailable_block

    ticker_map_path.write_text(json.dumps(raw, indent=2) + "\n")
    print(f"[suggest] Wrote {len(found)} new mapping(s) to {ticker_map_path}")


if __name__ == "__main__":
    main()
