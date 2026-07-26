"""
Fetches @grkportfolio's most recent posts via xAI's X Search tool (part of
the current Responses API), and asks Grok to extract any stock positions
mentioned as structured JSON.

NOTE: xAI deprecated the old `search_parameters`-on-`/v1/chat/completions`
approach (it now returns HTTP 410 Gone). Live search is now done via the
Responses API (`/v1/responses`) with a `tools: [{"type": "x_search"}]`
entry. Confirmed against https://docs.x.ai/developers/tools/x-search as of
this writing -- if this starts failing again, that's the page to re-check
first, since xAI's tool APIs are still evolving.
"""

import os
import json
import requests

XAI_API_KEY = os.environ["XAI_API_KEY"]
XAI_ENDPOINT = "https://api.x.ai/v1/responses"
GROK_PORTFOLIO_HANDLE = "grkportfolio"

EXTRACTION_PROMPT = """
Look at the most recent posts from the account @grkportfolio (also known
as "The Grok Portfolio"). Look specifically for posts that disclose stock
or ETF positions, weights, or performance updates.

Return ONLY a JSON object (no markdown, no commentary) in exactly this shape:

{
  "source_posts": [
    {"url": "<tweet url if available>", "posted_at": "<ISO8601 timestamp or best guess>"}
  ],
  "positions": [
    {"ticker": "NOW", "weight_pct": 12.6, "return_pct": 11.8}
  ],
  "notes": "<anything ambiguous or incomplete about this extraction>"
}

If a post shows only a partial list of positions, include only what is
explicitly stated -- do not guess or fill in the rest of a 15-position book
from memory. If no relevant posts are found, return an empty "positions" list.
"""


def _extract_text_from_responses_payload(payload: dict) -> str:
    """
    The Responses API returns an `output` list that can contain reasoning
    items, tool-call items, and message items mixed together. We only want
    the text content of the final assistant message(s). This walks the
    output list and concatenates any output_text content it finds.
    """
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


def fetch_latest_positions() -> dict:
    """
    Calls the xAI API with the X Search tool enabled, scoped to
    @grkportfolio, and asks Grok to return structured position data
    extracted from that account's recent posts.

    Returns a dict matching the EXTRACTION_PROMPT's JSON shape.
    Raises requests.HTTPError on a failed API call.
    """
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "grok-4.3",
        "input": [
            {"role": "user", "content": EXTRACTION_PROMPT}
        ],
        "tools": [
            {
                "type": "x_search",
                "allowed_x_handles": [GROK_PORTFOLIO_HANDLE],
            }
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


if __name__ == "__main__":
    # Quick manual test: `python scripts/fetch_grok_portfolio.py`
    result = fetch_latest_positions()
    print(json.dumps(result, indent=2))
