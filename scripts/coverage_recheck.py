"""
Periodic coverage reassessment -- NOT part of the trading pipeline.
Run this on a low-frequency schedule (weekly/monthly), separate from
the 6-hour mirror.yml trading workflow. Purely informational: never
places trades, never touches sub-accounts.

What it checks, every time it runs:
  1. Pulls the CURRENT ground-truth ticker set live from all 4
     portfolios' merged_state.json (not a stale snapshot -- holdings
     change as the AI portfolios rebalance).
  2. Pulls the LIVE Bitget Reality-token catalog and MEXC Ondo catalog
     (both grow over time as the issuers add coverage).
  3. Flags two things specifically, since these are the only two
     things that would actually change the Bitget-vs-MEXC decision:
       a) Tickers currently in target weights but NOT in your static
          ticker_map.json, even though they ARE now live on Bitget
          (map has gone stale -- update it)
       b) Any ticker MEXC now covers that Bitget does NOT (as of the
          last full check, MEXC was a strict subset of Bitget with
          zero unique tickers -- if that ever changes, it's the
          trigger to reconsider the toggle)

Sends a Telegram summary via notify.py's send_telegram_message if
configured, otherwise just prints to the Actions log.
"""

import json
import glob
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from notify import send_telegram_message  # reuses your existing Telegram setup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def get_current_ground_truth_tickers() -> set:
    tickers = set()
    pattern = os.path.join(REPO_ROOT, "portfolios", "*", "data", "merged_state.json")
    for f in glob.glob(pattern):
        data = json.load(open(f))
        for t in data:
            if t != "CASH":
                tickers.add(t.upper())
    return tickers


def get_static_ticker_map_symbols() -> set:
    """Whatever's currently mapped for Bitget execution, across all portfolios."""
    mapped = set()
    pattern = os.path.join(REPO_ROOT, "portfolios", "*", "config", "ticker_map.json")
    for f in glob.glob(pattern):
        try:
            data = json.load(open(f))
            mapped.update(k.upper() for k in data.keys())
        except FileNotFoundError:
            continue
    return mapped


def fetch_bitget_reality_tickers() -> set:
    url = "https://api.bitget.com/api/v3/market/instruments?category=SPOT"
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    result = set()
    for entry in data.get("data", []):
        is_reality = str(entry.get("isReality", "")).lower() == "yes"
        is_rwa = str(entry.get("isRwa", "")).upper() == "YES"
        if is_reality or is_rwa:
            base = entry.get("baseCoin", "")
            if base.lower().startswith("r") and len(base) > 1:
                result.add(base[1:].upper())
    return result


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
    ground_truth = get_current_ground_truth_tickers()
    mapped = get_static_ticker_map_symbols()

    try:
        bitget = fetch_bitget_reality_tickers()
    except Exception as e:
        bitget = None
        bitget_error = str(e)

    try:
        mexc = fetch_mexc_ondo_tickers()
    except Exception as e:
        mexc = None
        mexc_error = str(e)

    lines = ["[Coverage recheck] Periodic Bitget/MEXC reassessment:\n"]
    lines.append(f"Current live ticker set across all portfolios: {len(ground_truth)} tickers")

    if bitget is None:
        lines.append(f"Bitget fetch FAILED: {bitget_error}")
    else:
        lines.append(f"Bitget Reality-token catalog: {len(bitget)} symbols live")

    if mexc is None:
        lines.append(f"MEXC fetch FAILED: {mexc_error}")
    else:
        lines.append(f"MEXC Ondo catalog: {len(mexc)} symbols live")

    if bitget is not None:
        newly_covered_unmapped = (ground_truth & bitget) - mapped
        if newly_covered_unmapped:
            lines.append(
                f"\n!!! ACTION NEEDED: {len(newly_covered_unmapped)} ticker(s) are now live "
                f"on Bitget but missing from ticker_map.json: {sorted(newly_covered_unmapped)}"
            )
        else:
            lines.append("\nticker_map.json is up to date with live Bitget coverage.")

    if bitget is not None and mexc is not None:
        mexc_exclusive = (ground_truth & mexc) - bitget
        if mexc_exclusive:
            lines.append(
                f"\n!!! MEXC now covers tickers Bitget does NOT: {sorted(mexc_exclusive)} "
                f"-- worth reconsidering the venue decision."
            )
        else:
            lines.append(
                "\nMEXC still adds zero unique coverage beyond Bitget -- "
                "no reason to activate the MEXC integration yet."
            )

    summary = "\n".join(lines)
    print(summary)
    send_telegram_message(summary)


if __name__ == "__main__":
    main()
