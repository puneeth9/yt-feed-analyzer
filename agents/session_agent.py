from pathlib import Path

from playwright.sync_api import sync_playwright
from rich.console import Console

from orchestrator.state import FeedAnalyzerState

SESSION_PATH = Path("data/session.json")
USER_DATA_DIR = Path("data/chrome_profile")

_SIGNED_IN_SELECTOR = "button#avatar-btn"
_LOGIN_TIMEOUT_MS = 5 * 60 * 1000  # 5 minutes

console = Console()


def run_session_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """
    Checks for a saved browser session.
    If found: reuses it.
    If not found: opens real Chrome, waits until the user signs in
    (detected by the avatar button), then saves the session.
    """
    console.rule("[bold blue]Stage 1 of 4 — Session")

    if SESSION_PATH.exists():
        console.print("[green]✓[/green] Existing session found — reusing.")
        return {**state, "session_ready": True, "current_agent": "session"}

    console.print("[yellow]No session found.[/yellow] Launching Chrome for manual login...")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.new_page()
        page.goto("https://www.youtube.com")

        console.print("\n[bold]Chrome is open.[/bold] Please sign in to YouTube.")
        console.print("[dim]Waiting up to 5 minutes for login to complete...[/dim]")

        try:
            page.wait_for_selector(_SIGNED_IN_SELECTOR, timeout=_LOGIN_TIMEOUT_MS)
            console.print("[green]✓[/green] Login detected!")
        except Exception:
            context.close()
            raise RuntimeError("Login not detected within 5 minutes. Please try again.")

        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_PATH))
        console.print(f"[green]✓[/green] Session saved to [dim]{SESSION_PATH}[/dim]")
        context.close()

    return {**state, "session_ready": True, "current_agent": "session"}
