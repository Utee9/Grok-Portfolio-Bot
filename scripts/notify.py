"""
Sends a plain-text summary to your Telegram via a bot. Setup (one-time,
free): message @BotFather on Telegram, run /newbot, save the token it gives
you as the TELEGRAM_BOT_TOKEN secret. Then message your new bot once and
fetch your chat_id from https://api.telegram.org/bot<TOKEN>/getUpdates,
save that as TELEGRAM_CHAT_ID.
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


def build_run_summary(execution_results: list[dict], unmapped: list[dict], changes: list[dict] | None = None) -> str:
    if not execution_results and not unmapped:
        return "Grok Mirror: checked for updates, no rebalancing needed."

    lines = ["Grok Mirror run summary:"]

    if changes:
        lines.append("Detected changes in Grok's disclosed weights:")
        for c in changes:
            if c["action"] == "new":
                lines.append(f"  - {c['ticker']}: new position at {c['to_pct']}%")
            elif c["action"] in ("increase", "decrease"):
                lines.append(f"  - {c['ticker']}: {c['from_pct']}% -> {c['to_pct']}%")
            elif c["action"] == "closed":
                lines.append(f"  - {c['ticker']}: no longer mentioned (was {c['from_pct']}%)")
        lines.append("")

    if execution_results:
        lines.append("Trades placed to rebalance toward those weights:")
        for r in execution_results:
            lines.append(
                f"  - {r['side'].upper()} {r['ticker']} (${r['usdt_amount']}) "
                f"[{r['status']}] -- {r['reason']}"
            )

    if unmapped:
        lines.append("")
        lines.append("Unmapped tickers (no Bitget symbol -- add to ticker_map.json):")
        for u in unmapped:
            lines.append(f"  - {u['ticker']}")

    return "\n".join(lines)
