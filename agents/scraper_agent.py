import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from orchestrator.state import FeedAnalyzerState

SESSION_PATH = Path("data/session.json")
USER_DATA_DIR = Path("data/chrome_profile")
CHECKPOINT_DIR = Path("data/checkpoints")


def _scrape_current_short(page) -> dict:
    """Passively scrape metadata from the currently visible Short without clicking."""

    def safe_text(selector: str) -> str:
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else ""

    def safe_text_all(selector: str):
        els = page.query_selector_all(selector)
        return [el.inner_text().strip() for el in els if el.inner_text().strip()]

    # Title
    title = safe_text("h2.ytShortsVideoTitleViewModelShortsVideoTitle")
    if not title:
        title = safe_text("#shorts-player .title")
    if not title:
        title = safe_text("yt-shorts-video-title-view-model")

    # Channel name
    channel = safe_text("yt-shorts-channel-name-view-model .yt-core-attributed-string")
    if not channel:
        channel = safe_text(".shortsChannelName")
    if not channel:
        channel = safe_text("ytd-channel-name yt-formatted-string")

    # Hashtags — look for links that start with #
    hashtag_els = page.query_selector_all("a[href*='hashtag']")
    hashtags = []
    for el in hashtag_els:
        txt = el.inner_text().strip()
        if txt.startswith("#"):
            hashtags.append(txt)

    # Audio track
    audio_track = safe_text(".ytShortsVideoRendererAudioTrackTitleViewModelAudioTrackTitle")
    if not audio_track:
        audio_track = safe_text("yt-shorts-audio-metadata-view-model")

    # View count
    view_count = safe_text(".yt-spec-button-shape-next__button-text-content[aria-label*='view']")
    if not view_count:
        view_count = safe_text(".shortsLockupViewModelHostMetadataSubhead")

    # Suggested by YouTube label (passive check only)
    is_suggested = False
    suggested_els = page.query_selector_all("*")
    for el in suggested_els[:200]:  # limit scan
        try:
            txt = el.inner_text()
            if "Suggested by YouTube" in txt or "suggested by youtube" in txt.lower():
                is_suggested = True
                break
        except Exception:
            pass

    # Description — passive DOM read, no clicks
    description_raw = ""
    desc_el = page.query_selector("#description-text")
    if not desc_el:
        desc_el = page.query_selector("yt-attributed-string#attributed-description")
    if not desc_el:
        desc_el = page.query_selector(".shortsVideoRendererDescription")
    if desc_el:
        try:
            description_raw = desc_el.inner_text().strip()
        except Exception:
            description_raw = ""

    return {
        "title": title,
        "channel": channel,
        "hashtags": hashtags,
        "audio_track": audio_track,
        "view_count": view_count,
        "is_suggested": is_suggested,
        "description_raw": description_raw,
    }


def run_scraper_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Scroll through YouTube Shorts and collect raw metadata."""
    print("[scraper] Starting scraper agent...")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    target_count = state.get("target_count", 100)
    raw_shorts = list(state.get("raw_shorts", []))
    checkpoint = state.get("checkpoint", 0)

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            page = context.new_page()

            print("[scraper] Navigating to YouTube Shorts...")
            page.goto("https://www.youtube.com/shorts", wait_until="networkidle")
            time.sleep(2)

            for i in range(target_count):
                position = checkpoint + i

                # Randomized wait: 80% slow, 20% fast
                if random.random() < 0.80:
                    wait_time = random.uniform(1.5, 2.5)
                else:
                    wait_time = random.uniform(0.8, 1.2)
                time.sleep(wait_time)

                try:
                    short_data = _scrape_current_short(page)
                except Exception as exc:
                    print(f"[scraper] DOM scrape error at position {position}: {exc}")
                    short_data = {
                        "title": "",
                        "channel": "",
                        "hashtags": [],
                        "audio_track": "",
                        "view_count": "",
                        "is_suggested": False,
                        "description_raw": "",
                    }

                short_data["position"] = position
                short_data["timestamp"] = datetime.now(timezone.utc).isoformat()
                raw_shorts.append(short_data)

                print(
                    f"[scraper] [{position + 1}/{target_count}] "
                    f"title={short_data['title'][:40]!r} "
                    f"channel={short_data['channel']!r}"
                )

                # Checkpoint every 10 shorts
                if (i + 1) % 10 == 0:
                    cp_index = (position + 1) // 10
                    cp_path = CHECKPOINT_DIR / f"checkpoint_{cp_index}.json"
                    cp_path.write_text(json.dumps(raw_shorts, indent=2))
                    print(f"[scraper] Checkpoint saved: {cp_path}")

                # Scroll to next Short
                page.keyboard.press("ArrowDown")

            context.close()

    except Exception as exc:
        error_msg = f"Scraper failed at position {len(raw_shorts)}: {exc}"
        print(f"[scraper] FATAL: {error_msg}")
        return {
            **state,
            "raw_shorts": raw_shorts,
            "checkpoint": len(raw_shorts),
            "current_agent": "scraper",
            "error": error_msg,
        }

    print(f"[scraper] Done. Collected {len(raw_shorts)} Shorts.")
    return {
        **state,
        "raw_shorts": raw_shorts,
        "checkpoint": len(raw_shorts),
        "current_agent": "scraper",
    }
