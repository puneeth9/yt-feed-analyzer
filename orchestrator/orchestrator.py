import sys
from langgraph.graph import StateGraph, END

from orchestrator.state import FeedAnalyzerState
from agents.session_agent import run_session_agent
from agents.scraper_agent import run_scraper_agent
from agents.cleaner_agent import run_cleaner_agent
from agents.categorizer_agent import run_categorizer_agent
from agents.reporter_agent import run_reporter_agent


def orchestrator_node(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Pass-through node — routing happens in the conditional edge function."""
    return state


def route(state: FeedAnalyzerState) -> str:
    """
    Deterministic routing function.
    Same state always produces same next agent — no side effects.
    """
    if state.get("error") is not None:
        print(f"[orchestrator] Error detected: {state['error']}", file=sys.stderr)
        return END

    if not state.get("session_ready", False):
        return "session"

    if not state.get("raw_shorts"):
        return "scraper"

    if not state.get("cleaned_shorts"):
        return "cleaner"

    if not state.get("categorized_shorts"):
        return "categorizer"

    if state.get("status") == "done":
        return END

    # reporter hasn't run yet
    return "reporter"


def build_graph() -> StateGraph:
    graph = StateGraph(FeedAnalyzerState)

    # Nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("session", run_session_agent)
    graph.add_node("scraper", run_scraper_agent)
    graph.add_node("cleaner", run_cleaner_agent)
    graph.add_node("categorizer", run_categorizer_agent)
    graph.add_node("reporter", run_reporter_agent)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Conditional edges from orchestrator
    graph.add_conditional_edges(
        "orchestrator",
        route,
        {
            "session": "session",
            "scraper": "scraper",
            "cleaner": "cleaner",
            "categorizer": "categorizer",
            "reporter": "reporter",
            END: END,
        },
    )

    # Every agent routes back to orchestrator
    for agent in ("session", "scraper", "cleaner", "categorizer", "reporter"):
        graph.add_edge(agent, "orchestrator")

    return graph.compile()
