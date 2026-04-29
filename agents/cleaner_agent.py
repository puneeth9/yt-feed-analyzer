import os

import anthropic

from orchestrator.state import FeedAnalyzerState

CLEANER_PROMPT = (
    "Extract only the content-relevant part of this YouTube Short description. "
    "Remove all promotional content including social media links, follow requests, "
    "discount codes, merchandise links, and sponsor mentions. "
    "Return only the part that describes what the video is actually about. "
    "If there is no content-relevant part, return an empty string.\n\n"
    "Description: {description_raw}"
)


def run_cleaner_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Strip promotional noise from raw Short descriptions using Claude."""
    print("[cleaner] Starting cleaner agent...")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    raw_shorts = state.get("raw_shorts", [])
    cleaned_shorts = []

    for i, short in enumerate(raw_shorts):
        description_raw = short.get("description_raw", "").strip()

        if description_raw:
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=512,
                    messages=[
                        {
                            "role": "user",
                            "content": CLEANER_PROMPT.format(description_raw=description_raw),
                        }
                    ],
                )
                description_clean = response.content[0].text.strip()
            except Exception as exc:
                print(f"[cleaner] API error on short {i}: {exc}")
                description_clean = ""
        else:
            description_clean = ""

        cleaned_short = {**short, "description_clean": description_clean}
        cleaned_shorts.append(cleaned_short)

        if (i + 1) % 10 == 0:
            print(f"[cleaner] Cleaned {i + 1}/{len(raw_shorts)} Shorts...")

    print(f"[cleaner] Done. Cleaned {len(cleaned_shorts)} Shorts.")
    return {**state, "cleaned_shorts": cleaned_shorts, "current_agent": "cleaner"}
