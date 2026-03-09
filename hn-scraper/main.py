"""Hacker News Top Stories Scraper

Fetches top stories from the Hacker News API and saves them to a JSON file.
"""

import json
import urllib.request
import sys
from datetime import datetime, timezone

HN_API = "https://hacker-news.firebaseio.com/v0"
NUM_STORIES = 30


def fetch_json(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def fetch_top_stories(count: int = NUM_STORIES) -> list[dict]:
    story_ids = fetch_json(f"{HN_API}/topstories.json")[:count]
    stories = []

    for i, sid in enumerate(story_ids, 1):
        try:
            item = fetch_json(f"{HN_API}/item/{sid}.json")
            stories.append({
                "rank": i,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "score": item.get("score", 0),
                "by": item.get("by", ""),
                "comments": item.get("descendants", 0),
                "id": sid,
            })
            print(f"  [{i}/{count}] {item.get('title', '')[:60]}")
        except Exception as e:
            print(f"  [{i}/{count}] Failed to fetch story {sid}: {e}")

    return stories


def main():
    print(f"Fetching top {NUM_STORIES} Hacker News stories...")
    stories = fetch_top_stories()

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(stories),
        "stories": stories,
    }

    with open("hn_top_stories.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(stories)} stories to hn_top_stories.json")

    # Print summary
    print("\nTop 5:")
    for s in stories[:5]:
        print(f"  {s['rank']}. {s['title']} ({s['score']} pts, {s['comments']} comments)")


if __name__ == "__main__":
    main()
