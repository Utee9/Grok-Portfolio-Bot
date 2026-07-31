"""
Standalone script: scans one portfolio's target-weight tickers for any that
are unmapped OR previously confirmed unavailable on Bitget, re-checks them
against Bitget's live SPOT ticker list (public data, no credentials
needed), and writes any finds directly into that portfolio's
ticker_map.json on the current branch.

Never touches main directly -- the calling workflow wraps this diff in a
PR for human review before it can affect any real trade.
"""
import argparse
import json
import os

from portfolio_config import PortfolioConfig
from merge_sources import load_merged_state, build_target_weights
from ticker_mapping import load_ticker_map, load_cash_proxies, load_unavailable, suggest_mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio", required=True)
    args = parser.parse_args()

    portfolio = PortfolioConfig(args.portfolio)
    merged_state = load_merged_state(portfolio.merged_state_path)
    target_weights = build_target_weights(merged_state)

    if not target_weights:
        print(f"[suggest] No target weights known yet for {portfolio.name}.")
        return

    ticker_map = load_ticker_map(portfolio.ticker_map_path)
    cash_proxies = load_cash_proxies(portfolio.ticker_map_path)
    unavailable = load_unavailable(portfolio.ticker_map_path)

    to_check = [
        t for t in target_weights
        if t not in cash_proxies and (not ticker_map.get(t) or t in unavailable)
    ]
    if not to_check:
        print(f"[suggest] Nothing to check for {portfolio.name} -- all tickers already resolved.")
        return

    env = os.environ.copy()  # public market data -- no BITGET_* credentials needed
    found = {}
    for ticker in to_check:
        suggestion = suggest_mapping(ticker, env)
        if suggestion:
            found[ticker] = suggestion
            print(f"[suggest] {ticker} -> {suggestion}")
        else:
            print(f"[suggest] {ticker}: still not available on Bitget")

    if not found:
        print(f"[suggest] No new matches found for {portfolio.name}.")
        return

    raw = json.loads(portfolio.ticker_map_path.read_text())
    raw.update(found)
    unavailable_block = raw.get("_unavailable_on_bitget", {})
    for ticker in found:
        unavailable_block.pop(ticker, None)
    raw["_unavailable_on_bitget"] = unavailable_block

    portfolio.ticker_map_path.write_text(json.dumps(raw, indent=2) + "\n")
    print(f"[suggest] Wrote {len(found)} new mapping(s) to {portfolio.ticker_map_path}")


if __name__ == "__main__":
    main()
