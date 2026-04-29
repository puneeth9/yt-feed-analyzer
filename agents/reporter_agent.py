import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from orchestrator.state import FeedAnalyzerState

OUTPUT_DIR = Path("output")
console = Console()


def _quartile_label(index: int, total: int) -> str:
    q_size = total / 4
    q = math.floor(index / q_size)
    return f"Q{min(q + 1, 4)}"


def run_reporter_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Aggregate categorized Shorts and generate a markdown report."""
    print("[reporter] Starting reporter agent...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    shorts = state.get("categorized_shorts", [])
    total = len(shorts)

    if total == 0:
        print("[reporter] No categorized Shorts to report on.")
        return {**state, "status": "done", "current_agent": "reporter"}

    # ── 1. Category breakdown ────────────────────────────────────────────────
    category_counter: Counter = Counter(s.get("category", "uncategorized") for s in shorts)
    category_breakdown = {
        cat: {"count": cnt, "pct": round(cnt / total * 100, 1)}
        for cat, cnt in category_counter.most_common()
    }

    # ── 2. Top 10 channels ───────────────────────────────────────────────────
    channel_counter: Counter = Counter(
        s.get("channel", "unknown") for s in shorts if s.get("channel")
    )
    top_channels = channel_counter.most_common(10)

    # ── 3. Top 10 audio tracks ───────────────────────────────────────────────
    audio_counter: Counter = Counter(
        s.get("audio_track", "") for s in shorts if s.get("audio_track")
    )
    top_audio = audio_counter.most_common(10)

    # ── 4. Top hashtags ──────────────────────────────────────────────────────
    hashtag_counter: Counter = Counter()
    for s in shorts:
        for tag in s.get("hashtags", []):
            if tag:
                hashtag_counter[tag] += 1
    top_hashtags = hashtag_counter.most_common(20)

    # ── 5. Feed drift — quartile category distribution ───────────────────────
    quartile_data: dict[str, Counter] = {"Q1": Counter(), "Q2": Counter(), "Q3": Counter(), "Q4": Counter()}
    for idx, s in enumerate(shorts):
        q = _quartile_label(idx, total)
        quartile_data[q][s.get("category", "uncategorized")] += 1

    # ── 6. Suggestion vs organic ratio ───────────────────────────────────────
    suggested_count = sum(1 for s in shorts if s.get("is_suggested", False))
    organic_count = total - suggested_count
    suggested_pct = round(suggested_count / total * 100, 1)
    organic_pct = round(organic_count / total * 100, 1)

    # ── 7. Confidence distribution per category ──────────────────────────────
    confidence_by_cat: dict[str, list] = defaultdict(list)
    for s in shorts:
        cat = s.get("category", "uncategorized")
        conf = s.get("confidence", 0.0)
        confidence_by_cat[cat].append(conf)
    avg_confidence = {
        cat: round(sum(vals) / len(vals), 3)
        for cat, vals in confidence_by_cat.items()
    }

    # ── Build markdown ───────────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUTPUT_DIR / f"report_{timestamp}.md"

    lines = [
        f"# YouTube Shorts Feed Analysis Report",
        f"",
        f"Generated: {timestamp}  |  Shorts analyzed: {total}",
        f"",
        f"---",
        f"",
        f"## 1. Category Breakdown",
        f"",
        f"| Category | Count | % of Feed |",
        f"|----------|-------|-----------|",
    ]
    for cat, info in sorted(category_breakdown.items(), key=lambda x: -x[1]["count"]):
        lines.append(f"| {cat} | {info['count']} | {info['pct']}% |")

    lines += [
        f"",
        f"## 2. Top 10 Channels",
        f"",
        f"| Rank | Channel | Appearances |",
        f"|------|---------|-------------|",
    ]
    for rank, (ch, cnt) in enumerate(top_channels, 1):
        lines.append(f"| {rank} | {ch} | {cnt} |")

    lines += [
        f"",
        f"## 3. Top 10 Audio Tracks",
        f"",
        f"| Rank | Audio Track | Appearances |",
        f"|------|-------------|-------------|",
    ]
    for rank, (track, cnt) in enumerate(top_audio, 1):
        lines.append(f"| {rank} | {track} | {cnt} |")

    lines += [
        f"",
        f"## 4. Top Hashtags",
        f"",
        f"| Hashtag | Count |",
        f"|---------|-------|",
    ]
    for tag, cnt in top_hashtags:
        lines.append(f"| {tag} | {cnt} |")

    lines += [
        f"",
        f"## 5. Feed Drift Analysis (Quartiles)",
        f"",
        f"Category distribution across feed position quartiles:",
        f"",
    ]
    all_cats = sorted(category_counter.keys())
    header = "| Category | Q1 | Q2 | Q3 | Q4 |"
    separator = "|----------|----|----|----|----|"
    lines += [header, separator]
    for cat in all_cats:
        row = f"| {cat} | {quartile_data['Q1'].get(cat, 0)} | {quartile_data['Q2'].get(cat, 0)} | {quartile_data['Q3'].get(cat, 0)} | {quartile_data['Q4'].get(cat, 0)} |"
        lines.append(row)

    lines += [
        f"",
        f"## 6. Suggestion vs Organic Ratio",
        f"",
        f"| Type | Count | % |",
        f"|------|-------|---|",
        f"| Suggested by YouTube | {suggested_count} | {suggested_pct}% |",
        f"| Organic | {organic_count} | {organic_pct}% |",
        f"",
        f"## 7. Confidence Distribution by Category",
        f"",
        f"| Category | Avg Confidence |",
        f"|----------|----------------|",
    ]
    for cat, avg in sorted(avg_confidence.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {avg} |")

    report_content = "\n".join(lines) + "\n"
    report_path.write_text(report_content)
    print(f"[reporter] Report saved to {report_path}")

    # ── Rich CLI summary ─────────────────────────────────────────────────────
    console.rule("[bold cyan]YouTube Shorts Feed Analysis")
    console.print(f"[dim]Analyzed [bold]{total}[/bold] Shorts[/dim]\n")

    # Category table
    cat_table = Table(title="Category Breakdown", box=box.SIMPLE_HEAD)
    cat_table.add_column("Category", style="cyan")
    cat_table.add_column("Count", justify="right")
    cat_table.add_column("% of Feed", justify="right")
    for cat, info in sorted(category_breakdown.items(), key=lambda x: -x[1]["count"]):
        cat_table.add_row(cat, str(info["count"]), f"{info['pct']}%")
    console.print(cat_table)

    # Channels table
    ch_table = Table(title="Top 10 Channels", box=box.SIMPLE_HEAD)
    ch_table.add_column("Channel", style="green")
    ch_table.add_column("Appearances", justify="right")
    for ch, cnt in top_channels:
        ch_table.add_row(ch, str(cnt))
    console.print(ch_table)

    # Suggestion ratio
    console.print(
        f"\n[bold]Suggested by YouTube:[/bold] {suggested_count} ({suggested_pct}%)  "
        f"[bold]Organic:[/bold] {organic_count} ({organic_pct}%)\n"
    )

    console.print(f"[bold green]Report:[/bold green] {report_path.resolve()}")

    return {
        **state,
        "status": "done",
        "current_agent": "reporter",
    }
