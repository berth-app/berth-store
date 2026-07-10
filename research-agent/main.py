"""Research Agent — a scheduled research report, written by Claude.

Give it a topic; it uses Claude's built-in web search to gather current
information and writes a dated markdown report to ./reports/. Point Berth's
scheduler at it (`berth schedule add research-agent "@daily"`) for a standing
briefing on anything you want to track — a competitor, a technology, a market.

Runs on your own machine with your own API key. The topic and report never
leave your infrastructure except for the web searches Claude runs on your
behalf.

Required env vars:
  ANTHROPIC_API_KEY   API key from console.anthropic.com
  RESEARCH_TOPIC      What to research (e.g. "developments in NATS messaging")

Optional env vars:
  RESEARCH_MODEL      Claude model id (default: claude-opus-4-8)
  RESEARCH_MAX_SEARCHES  Cap on web searches per run (default: 8)
  REPORTS_DIR         Where to write reports (default: ./reports)
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

MODEL = os.environ.get("RESEARCH_MODEL", "claude-opus-4-8").strip()
MAX_SEARCHES = int(os.environ.get("RESEARCH_MAX_SEARCHES", "8"))
# Server-side tool loops can pause and need re-sending; bound how many times.
MAX_CONTINUATIONS = 6


def die(msg: str) -> "NoReturn":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set — get one at https://console.anthropic.com")
    topic = os.environ.get("RESEARCH_TOPIC", "").strip()
    if not topic:
        die("RESEARCH_TOPIC not set — tell the agent what to research")

    reports_dir = Path(os.environ.get("REPORTS_DIR", "./reports")).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"═══ Research Agent ({MODEL}) ═══")
    print(f"Topic: {topic}")
    print(f"Date:  {today}\n")

    prompt = (
        f"Research this topic and write a briefing: {topic}\n\n"
        f"Today is {today}. Search the web for the most current, credible "
        "information. Then write a well-structured markdown report with: a "
        "one-paragraph executive summary, the key findings as sections, and a "
        "sources list with links. Prioritize recent developments over "
        "background. Output only the markdown report — no preamble."
    )
    messages = [{"role": "user", "content": prompt}]
    tools = [{
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": MAX_SEARCHES,
    }]

    total_in = total_out = 0
    response = None
    for _ in range(MAX_CONTINUATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            tools=tools,
            messages=messages,
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens

        for block in response.content:
            if block.type == "server_tool_use" and block.name == "web_search":
                query = block.input.get("query", "")
                print(f"  🔎 {query}")

        # Server-side tool loop hit its per-turn limit — re-send to resume.
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break
    else:
        print("⚠ Search loop did not converge; writing what we have.")

    report = "".join(
        b.text for b in (response.content if response else []) if b.type == "text"
    ).strip()
    if not report:
        die("no report text produced — try a narrower topic or more searches")

    out_path = reports_dir / f"{today}-{slugify(topic)}.md"
    out_path.write_text(f"# {topic}\n\n_Researched {today}_\n\n{report}\n")

    cost = total_in / 1e6 * 5.0 + total_out / 1e6 * 25.0
    print(f"\n✓ Report written to {out_path}")
    print(f"─── {total_in:,} in + {total_out:,} out tokens · ~${cost:.3f} ───")


def slugify(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "report"


if __name__ == "__main__":
    main()
