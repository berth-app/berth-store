"""PR Review Agent — Claude reviews your open pull requests, on a schedule.

Each run, it checks a GitHub repo for open PRs it hasn't reviewed yet (or that
have new commits since its last review), reads the diff, and posts a review
comment with Claude's feedback. It keeps a small state file so it never
double-reviews the same commit.

Point Berth's scheduler at it — `berth schedule add pr-review-agent "@hourly"`
— and it becomes a tireless first-pass reviewer running on your own machine
with your own keys. Nothing leaves your infra except the GitHub API calls and
the diff sent to Claude.

Required env vars:
  ANTHROPIC_API_KEY   API key from console.anthropic.com
  GITHUB_TOKEN        A GitHub token with repo access (repo scope, or PR read +
                      write for fine-grained tokens)
  GITHUB_REPO         owner/name, e.g. "berth-app/berth"

Optional env vars:
  REVIEW_MODEL        Claude model id (default: claude-opus-4-8)
  REVIEW_MAX_DIFF     Max diff chars sent to Claude (default: 40000)
  STATE_FILE          Where to track reviewed commits (default: ./reviewed.json)
  DRY_RUN             If "true", print the review instead of posting it
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import anthropic

MODEL = os.environ.get("REVIEW_MODEL", "claude-opus-4-8").strip()
MAX_DIFF = int(os.environ.get("REVIEW_MAX_DIFF", "40000"))
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"
API = "https://api.github.com"


def die(msg: str) -> "NoReturn":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def gh(path: str, token: str, *, accept: str = "application/vnd.github+json",
       method: str = "GET", body: dict | None = None) -> object:
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "berth-pr-review-agent")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return raw.decode() if "diff" in accept else json.loads(raw)
    except urllib.error.HTTPError as e:
        die(f"GitHub API {e.code} on {method} {path}: {e.read().decode()[:200]}")


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def review_pr(client: anthropic.Anthropic, title: str, diff: str) -> str:
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n\n[diff truncated]"
    prompt = (
        f"Review this pull request titled {title!r}. Focus on correctness bugs, "
        "security issues, and clear design problems — not style nits. Be "
        "specific: name the file and describe the failure. If it looks good, "
        "say so briefly. Keep it concise and actionable.\n\n"
        f"```diff\n{diff}\n```"
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set — get one at https://console.anthropic.com")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        die("GITHUB_TOKEN not set — create one at github.com/settings/tokens")
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if "/" not in repo:
        die("GITHUB_REPO not set — expected owner/name, e.g. berth-app/berth")

    state_file = Path(os.environ.get("STATE_FILE", "./reviewed.json")).resolve()
    state = load_state(state_file)
    client = anthropic.Anthropic()

    print(f"═══ PR Review Agent ({MODEL}) ═══")
    print(f"Repo: {repo}{'  (dry run)' if DRY_RUN else ''}\n")

    prs = gh(f"/repos/{repo}/pulls?state=open&per_page=50", token)
    if not prs:
        print("No open pull requests.")
        return

    reviewed_now = 0
    for pr in prs:
        num = pr["number"]
        head = pr["head"]["sha"]
        # Skip if we already reviewed this exact commit.
        if state.get(str(num)) == head:
            print(f"  #{num} already reviewed at {head[:7]} — skipping")
            continue

        print(f"  #{num} {pr['title']} — reviewing {head[:7]}")
        diff = gh(f"/repos/{repo}/pulls/{num}", token,
                  accept="application/vnd.github.v3.diff")
        review = review_pr(client, pr["title"], diff)

        if DRY_RUN:
            print(f"\n--- review for #{num} ---\n{review}\n")
        else:
            gh(f"/repos/{repo}/issues/{num}/comments", token, method="POST",
               body={"body": f"🤖 **Claude review**\n\n{review}"})
            print(f"    posted review to #{num}")

        state[str(num)] = head
        reviewed_now += 1

    if not DRY_RUN:
        state_file.write_text(json.dumps(state, indent=2))
    print(f"\n✓ Reviewed {reviewed_now} PR(s) this run.")


if __name__ == "__main__":
    main()
