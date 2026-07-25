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


def build_run_summary(execution_results: list[dict], unmapped: list[dict]) -> str:
    if not execution_results and not unmapped:
        return "Grok Mirror: checked for updates, no position changes detected."

    lines = ["Grok Mirror run summary:"]

    for r in execution_results:
        lines.append(
            f"- {r['side'].upper()} {r['ticker']} (${r['usdt_amount']}) "
            f"[{r['status']}] -- {r['reason']}"
        )

    if unmapped:
        lines.append("")
        lines.append("Unmapped tickers (no Bitget symbol -- add to ticker_map.json):")
        for u in unmapped:
            lines.append(f"- {u['ticker']} ({u['action']})")

    return "\n".join(lines)
