# yt-feed-analyzer

A multi-agent CLI tool that scrolls your YouTube Shorts feed, analyzes every video with Claude, and produces a structured report of what the algorithm is actually serving you — by category, channel, hashtag, audio track, and feed position.

---

## Overview

Most people have no visibility into what their Shorts feed contains or how it has drifted over time. `yt-feed-analyzer` gives you a quantified snapshot: run it against 100 (or up to 500) Shorts, and get back a breakdown of content categories, top channels, trending audio, hashtag clusters, and the ratio of organic vs. YouTube-suggested content.

The tool is built as a pipeline of five specialized agents, each responsible for one stage of the analysis. Agents communicate through a shared state object and are orchestrated by a LangGraph state machine — meaning the pipeline is resumable, each stage can be developed and tested independently, and adding new agents requires no changes to existing ones.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Orchestrator                        │
│              (LangGraph StateGraph router)               │
└────────┬────────┬───────────┬─────────────┬─────────────┘
         │        │           │             │
         ▼        ▼           ▼             ▼
     Session   Scraper    Cleaner     Categorizer   Reporter
     Agent     Agent      Agent         Agent        Agent
```

The orchestrator holds no business logic. It inspects the shared state after every agent completes and routes to the next one deterministically. If an agent sets an `error` field, the pipeline halts immediately.

### Agents

| Agent | Responsibility |
|---|---|
| **Session** | Checks for a saved browser session. If none exists, opens real Chrome and waits for the user to log in, then persists the session to disk. Subsequent runs skip this step entirely. |
| **Scraper** | Launches Chrome with the saved session, navigates to `youtube.com/shorts`, and scrolls through the feed using keyboard events. Passively reads DOM metadata (title, channel, hashtags, audio track, view count, description) for each Short without clicking anything. Saves checkpoints every 10 Shorts. |
| **Cleaner** | Sends each raw description through Claude to strip promotional noise — social links, discount codes, sponsor mentions — and returns only the content-relevant text. |
| **Categorizer** | Sends the full metadata of each Short (title, channel, hashtags, audio, cleaned description) through Claude and receives a structured category, subcategory, confidence score, and reasoning. |
| **Reporter** | Aggregates all categorized Shorts and produces a markdown report plus a rich CLI summary covering: category breakdown, top channels, top audio tracks, top hashtags, feed drift by quartile, suggestion vs. organic ratio, and per-category confidence. |

### Shared State

All agents read from and write to a single `FeedAnalyzerState` TypedDict. The orchestrator routes based on which fields are populated:

```python
class FeedAnalyzerState(TypedDict):
    session_ready: bool
    target_count: int
    raw_shorts: List[dict]         # populated by Scraper
    checkpoint: int
    cleaned_shorts: List[dict]     # populated by Cleaner
    categorized_shorts: List[dict] # populated by Categorizer
    current_agent: str
    error: Optional[str]
    status: str                    # "running" | "done" | "failed"
```

Because state is the only communication channel, agents are fully decoupled — no direct imports between them.

---

## File Structure

```
yt-feed-analyzer/
├── main.py                        # CLI entry point (Typer)
│
├── orchestrator/
│   ├── orchestrator.py            # LangGraph StateGraph + routing logic
│   └── state.py                   # Shared state TypedDicts
│
├── agents/
│   ├── session_agent.py           # Browser session management
│   ├── scraper_agent.py           # Playwright scraper
│   ├── cleaner_agent.py           # Claude description cleaner
│   ├── categorizer_agent.py       # Claude categorizer
│   └── reporter_agent.py          # Report generator
│
├── data/                          # Runtime data (gitignored)
│   ├── session.json               # Saved browser session
│   ├── chrome_profile/            # Persistent Chrome profile
│   ├── checkpoints/               # Per-10-short scrape checkpoints
│   └── categorized/               # Raw categorized JSON outputs
│
├── output/                        # Generated reports (gitignored)
│   └── report_<timestamp>.md
│
├── requirements.txt
├── .env                           # ANTHROPIC_API_KEY (gitignored)
└── .gitignore
```

---

## Setup

**1. Clone and create a virtual environment**
```bash
git clone <repo-url>
cd yt-feed-analyzer
python3 -m venv venv
source venv/bin/activate
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**3. Add your Anthropic API key**
```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

**4. Run**
```bash
python3 main.py analyze --count 100
```

On the first run a Chrome window will open. Sign in to YouTube — the tool detects login automatically and saves the session. All subsequent runs reuse it.

---

## Usage

```
Usage: main.py analyze [OPTIONS]

  Scroll YouTube Shorts, analyze with Claude, and generate a categorized report.

Options:
  -n, --count INTEGER RANGE [10<=x<=500]  Number of Shorts to scroll  [default: 100]
  --help                                  Show this message and exit.
```

**Analyze 200 Shorts:**
```bash
python3 main.py analyze --count 200
```

**Force a fresh login (e.g. to switch accounts):**
```bash
rm -rf data/session.json data/chrome_profile/
python3 main.py analyze --count 100
```

---

## Output

Each run produces a timestamped markdown report in `output/` and prints a rich CLI summary:

- **Category Breakdown** — distribution of content categories across all Shorts
- **Top 10 Channels** — most-appearing channels in the feed
- **Top 10 Audio Tracks** — trending sounds and music
- **Top Hashtags** — most common hashtags (up to 20)
- **Feed Drift Analysis** — how the category mix shifts across Q1→Q4 of the feed, revealing algorithmic drift as you scroll deeper
- **Suggestion vs. Organic Ratio** — how much of the feed is YouTube-suggested vs. channels you follow
- **Confidence by Category** — Claude's average classification confidence per category

---

## Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headed browser automation for scraping |
| `playwright-stealth` | Suppresses automation signals so Google accepts login |
| `anthropic` | Claude API for cleaning and categorization |
| `langgraph` | Agent orchestration as a typed state machine |
| `typer` | CLI interface |
| `rich` | Progress bars, tables, and terminal formatting |
| `python-dotenv` | `.env` file loading |

---

## Next Steps

### Accurate Channel Name Extraction
The scraper currently misses most channel names because YouTube's Shorts DOM renders the channel info inside a dynamically loaded component. The fix involves identifying the correct stable selector (likely `yt-shorts-channel-name-view-model` or the `@handle` link anchor) and adding a short post-navigation wait to ensure the component is mounted before reading. Channel data would unlock the top-channels report and enable per-creator analysis.

### Richer Metadata Without Feed Manipulation
Several signals can be extracted passively without interacting in ways that would influence the algorithm:

- **Like and comment counts** — visible in the action bar DOM without clicking
- **Video duration** — available in the player metadata element
- **Channel subscriber count** — sometimes rendered in the channel info component
- **Upload date and recency** — available in some Short metadata nodes
- **Hashtag vs. title topic alignment** — whether the hashtags actually match the content (a signal of spam or clickbait)

The core constraint is to keep all extraction strictly read-only — no likes, no follows, no searches, no replays — so the scraping session does not alter the feed being measured.

### Better Categorization
The current categorizer makes one API call per Short. Improvements:

- **Batch prompting** — send 10–20 Shorts per call with structured output to reduce latency and cost by roughly 10x
- **Two-tier taxonomy** — move from coarse labels (`Sports`, `Education`) to a structured taxonomy (e.g. `Sports > Cricket`, `Education > Personal Finance`) for more actionable reports
- **Confidence thresholding** — Shorts below a confidence threshold (e.g. < 0.6) could trigger a second-pass classification with additional context or a different prompt
- **User-defined categories** — let the user supply their own category set in a config file so the taxonomy aligns with their specific interests

### Feed Preference Analysis
Once baseline data exists across multiple runs, the tool could:

- **Detect algorithmic drift** — compare category distributions run-over-run to surface how the feed is shifting over time
- **Identify over-represented content** — flag categories appearing at a frequency disproportionate to stated preferences
- **Infer engagement signals** — content served in Q1 of the feed is what the algorithm predicts highest engagement on; comparing Q1 vs. Q4 composition reveals what the algorithm thinks you want vs. what it falls back to

### Feed Alteration Based on User Preferences
A future `tune` command could close the loop. Given a target category distribution defined by the user (e.g. "more Education, less Suggested content"), it would:

1. Identify Shorts in unwanted categories from the latest run
2. Simulate disinterest signals (fast skip, "Not interested") via Playwright
3. Identify Shorts in desired categories and simulate organic engagement (normal dwell time)
4. Re-run the analyzer after several days to measure the resulting feed shift

This would be opt-in and transparent — the user defines the target distribution, the tool executes the interactions, and the analyzer measures the outcome against the baseline.
