"""
Fetches @grkportfolio's most recent posts via xAI's live X-search, and asks
Grok to extract any stock positions mentioned as structured JSON.

IMPORTANT: xAI's exact request schema for enabling live X-search (as opposed
to a plain chat completion) has changed more than once as the API has
evolved. Treat the request body below as a best-effort starting point, not
a guaranteed-correct call -- verify the current field names against
https://docs.x.ai before your first real run, and adjust as needed.
As of writing, xAI bills live-search usage as a per-call "tool" fee on top
of normal token costs (see docs.x.ai/docs/models for current rates).
"""

import os
import json
import requests

XAI_API_KEY = os.environ["XAI_API_KEY"]
XAI_ENDPOINT = "https://api.x.ai/v1/chat/completions"

EXTRACTION_PROMPT = """
Search X for the most recent posts from the account @grkportfolio (also
known as "The Grok Portfolio"). Look specifically for posts that disclose
stock or ETF positions, weights, or performance updates.

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


def fetch_latest_positions() -> dict:
    """
    Calls the xAI API with live X-search enabled and asks Grok to return
    structured position data extracted from @grkportfolio's recent posts.

    Returns a dict matching the EXTRACTION_PROMPT's JSON shape.
    Raises requests.HTTPError on a failed API call.
    """
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "grok-4.3",
        "messages": [
            {"role": "user", "content": EXTRACTION_PROMPT}
        ],
        # NOTE: verify this is still the correct way to request live X-search
        # in the current xAI API -- some versions of the API expose this as a
        # top-level "search_parameters" object rather than a "tools" entry.
        "search_parameters": {
            "mode": "auto",
            "sources": [{"type": "x"}]
        },
        "temperature": 0,
    }

    response = requests.post(XAI_ENDPOINT, headers=headers, json=body, timeout=60)
    response.raise_for_status()

    raw_content = response.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Grok did not return valid JSON. Raw response was:\n{raw_content}"
        ) from exc


if __name__ == "__main__":
    # Quick manual test: `python scripts/fetch_grok_portfolio.py`
    result = fetch_latest_positions()
    print(json.dumps(result, indent=2))
