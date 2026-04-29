from pathlib import Path

from playwright.sync_api import sync_playwright

from orchestrator.state import FeedAnalyzerState

SESSION_PATH = Path("data/session.json")
USER_DATA_DIR = Path("data/chrome_profile")

# Selector visible only when signed in to YouTube
_SIGNED_IN_SELECTOR = "button#avatar-btn"
_LOGIN_TIMEOUT_MS = 5 * 60 * 1000  # 5 minutes


def run_session_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """
    Checks for a saved browser session.
    If found: reuses it.
    If not found: opens real Chrome, waits until the user signs in
    (detected by the avatar button), then saves the session.
    """
    print("[session] Starting session agent...")

    if SESSION_PATH.exists():
        print(f"[session] Found existing session at {SESSION_PATH}. Reusing.")
        return {**state, "session_ready": True, "current_agent": "session"}

    print("[session] No session found. Launching Chrome for manual login...")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # launch_persistent_context uses a real Chrome profile directory,
        # which passes Google's "secure browser" check.
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.new_page()

        page.goto("https://www.youtube.com")

        print("\n[session] Chrome is open. Please sign in to YouTube.")
        print(f"[session] Waiting up to 5 minutes for login to complete...")

        try:
            page.wait_for_selector(_SIGNED_IN_SELECTOR, timeout=_LOGIN_TIMEOUT_MS)
            print("[session] Login detected!")
        except Exception:
            context.close()
            raise RuntimeError(
                "Login not detected within 5 minutes. Please try again."
            )

        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_PATH))
        print(f"[session] Session saved to {SESSION_PATH}")

        context.close()

    return {**state, "session_ready": True, "current_agent": "session"}
