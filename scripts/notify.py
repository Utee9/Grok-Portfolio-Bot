"""
Sends a plain-text summary to your Telegram via a bot -- shared across all
portfolios, with each message labelled by which portfolio it's from.

Every run now sends a message, even a quiet one -- always showing the
current known target weights for that portfolio, so you have a running
visibility check that the pipeline is actually alive and what it currently
believes the portfolio looks like, not just alerts when something changes.
"""

import os
import requests


def send_telegram_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[notify] Telegram not configured -- skipping alert. Message was:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)

    if not response.ok:
        print(f"[notify] Telegram send failed: {response.status_code} {response.text}")


def _format_weights(target_weights: dict) -> list[str]:
    if not target_weights:
        return ["  (no target weights known yet)"]

    sorted_weights = sorted(target_weights.items(), key=lambda item: -item[1])
    return [f"  {ticker}: {weight}%" for ticker, weight in sorted_weights]


def build_run_summary(
    display_name: str,
    target_weights: dict,
    execution_results: list[dict],
    unmapped: list[str],
    narrative_actions: list[dict] | None = None,
    tracking_only: bool = False,
) -> str:
    header = f"[{display_name}] "
    lines = [f"{header}run summary:"]

    mode_note = " (tracking-only -- no Bitget sub-account configured yet)" if tracking_only else ""
    lines.append(f"Current target weights{mode_note}:")
    lines.extend(_format_weights(target_weights))
    lines.append("")

    if execution_results:
        lines.append("Trades placed to rebalance toward those weights:")
        for r in execution_results:
            lines.append(
                f"  - {r['side'].upper()} {r['ticker']} (${r['usdt_amount']}) "
                f"[{r['status']}] -- {r['reason']}"
            )
        lines.append("")
    elif not tracking_only:
        lines.append("No trades needed this run -- already at target weights.")
        lines.append("")

    if narrative_actions:
        lines.append("Narrative actions mentioned (no weight -- NOT auto-traded, review manually):")
        for n in narrative_actions:
            price_note = f" @ ~${n['approx_price']}" if n.get("approx_price") else ""
            lines.append(f"  - {n['action'].upper()} {n['ticker']}{price_note} -- {n.get('stated_reason', '')}")
        lines.append("")

    if unmapped:
        lines.append("Unmapped tickers (no Bitget symbol -- add to ticker_map.json):")
        for t in unmapped:
            lines.append(f"  - {t}")

    return "\n".join(lines).rstrip()
