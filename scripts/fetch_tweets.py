"""
Fetches a portfolio's most recent disclosed positions via xAI's X Search
tool, scoped to a specific handle. If no handle is configured for a
portfolio (x_handle is None -- e.g. DeepSeek/GPT, which have no live
dedicated account), this is skipped entirely and an empty extraction is
returned, so the pipeline falls back to manual_override.json alone.

NOTE: xAI deprecated the old `search_parameters`-on-`/v1/chat/completions`
approach (it now returns HTTP 410 Gone). Live search is done via the
Responses API (`/v1/responses`) with a `tools: [{"type": "x_search"}]`
entry. Confirmed against https://docs.x.ai/developers/tools/x-search as of
this writing -- if this starts failing again, that's the page to re-check
first, since xAI's tool APIs are still evolving.
"""

import os
import json
import requests

XAI_ENDPOINT = "https://api.x.ai/v1/responses"

EMPTY_EXTRACTION = {"source_posts": [], "positions": [], "narrative_actions": [], "notes": ""}


def _build_prompt(handle: str) -> str:
    return f"""
Look at the most recent posts from the account @{handle}. We only care
about posts that disclose ACTUAL portfolio activity -- not general market
commentary, not analysis of a stock the account doesn't hold, not replies
to other people's posts.

Classify each relevant post into exactly one of two categories:

1. WEIGHT DISCLOSURE -- a post that states or implies a specific
   percentage weight for one or more positions (e.g. a table of "NOW 12.6%",
   or "ZETA is now 9.5% of the book"). These go in "positions".

2. NARRATIVE ACTION -- a post that describes a buy or sell in prose,
   without a specific weight number (e.g. "I added DHT at about $17.75 to
   hedge against a supply shock"). These go in "narrative_actions" instead
   -- do NOT invent a weight_pct for these.

Ignore posts that are pure commentary/analysis with no disclosed action of
its own money.

Return ONLY a JSON object (no markdown, no commentary) in exactly this shape:

{{
  "source_posts": [
    {{"url": "<tweet url if available>", "posted_at": "<ISO8601 timestamp or best guess>"}}
  ],
  "positions": [
    {{"ticker": "NOW", "weight_pct": 12.6, "return_pct": 11.8}}
  ],
  "narrative_actions": [
    {{"ticker": "DHT", "action": "buy", "approx_price": 17.75, "stated_reason": "hedge against oil supply shock", "posted_at": "2026-07-14"}}
  ],
  "notes": "<anything ambiguous or incomplete about this extraction>"
}}

If a post shows only a partial weight table, include only what is
explicitly stated -- do not guess or fill in the rest of a 15-position book
from memory. If no relevant posts are found, return empty lists for both
"positions" and "narrative_actions".
"""


def _extract_text_from_responses_payload(payload: dict) -> str:
    text_parts = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content_piece in item.get("content", []):
            if content_piece.get("type") == "output_text":
                text_parts.append(content_piece.get("text", ""))

    if not text_parts:
        raise ValueError(
            f"Could not find any output_text in the Responses API payload. "
            f"Full payload was:\n{json.dumps(payload, indent=2)}"
        )
    return "".join(text_parts)


def fetch_latest_positions(x_handle: str | None) -> dict:
    """
    Returns a dict matching EMPTY_EXTRACTION's shape. If x_handle is None,
    skips the API call entirely (manual-only portfolio).
    """
    if not x_handle:
        return dict(EMPTY_EXTRACTION)

    xai_api_key = os.environ["XAI_API_KEY"]  # shared across all portfolios
    headers = {
        "Authorization": f"Bearer {xai_api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "grok-4.3",
        "input": [
            {"role": "user", "content": _build_prompt(x_handle)}
        ],
        "tools": [
            {"type": "x_search", "allowed_x_handles": [x_handle]}
        ],
        "temperature": 0,
    }

    response = requests.post(XAI_ENDPOINT, headers=headers, json=body, timeout=90)
    response.raise_for_status()

    raw_content = _extract_text_from_responses_payload(response.json())

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Grok did not return valid JSON. Raw text response was:\n{raw_content}"
        ) from exc
