from typing import List, Optional
from typing_extensions import TypedDict


class FeedAnalyzerState(TypedDict):
    session_ready: bool
    target_count: int
    raw_shorts: List[dict]
    checkpoint: int
    cleaned_shorts: List[dict]
    categorized_shorts: List[dict]
    current_agent: str
    error: Optional[str]
    status: str  # "running" | "failed" | "done"


class ScraperPrivateState(TypedDict):
    browser_context: object
    scroll_speed: float
    retry_count: int


class CategorizerPrivateState(TypedDict):
    llm_token_usage: int
    failed_shorts: List[dict]
