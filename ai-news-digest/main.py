"""Daily AI & Tech News Digest

Queries Perplexity AI for today's top tech and AI news,
then sends a formatted digest to Telegram.

Required env vars:
  PERPLEXITY_API_KEY  - API key from perplexity.ai
  TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
  TELEGRAM_CHAT_ID    - Chat or channel ID to send to

Schedule with: berth schedule add <project> "@daily"
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4096


def validate_env():
    missing = []
    if not PERPLEXITY_API_KEY:
        missing.append("PERPLEXITY_API_KEY (get one at https://perplexity.ai/settings/api)")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN (create a bot via @BotFather on Telegram)")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID (send /start to your bot, then check https://api.telegram.org/bot<token>/getUpdates)")
    if missing:
        print("Missing required environment variables:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)


def fetch_news() -> str:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    resp = requests.post(
        PERPLEXITY_URL,
        headers={
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise tech news curator. Use Markdown formatting suitable for Telegram (bold with *, links with [text](url)). No images.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Today is {today}. Give me the top 10 tech and AI news stories from today. "
                        "For each story: a bold headline, 1-2 sentence summary, and source link if available. "
                        "Number them 1-10."
                    ),
                },
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def send_telegram(text: str):
    url = TELEGRAM_URL.format(token=TELEGRAM_BOT_TOKEN)

    # Split long messages at line boundaries
    chunks = []
    if len(text) <= MAX_MESSAGE_LEN:
        chunks = [text]
    else:
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX_MESSAGE_LEN:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)

    for i, chunk in enumerate(chunks):
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if not resp.ok:
            print(f"Telegram API error (chunk {i+1}): {resp.status_code} {resp.text}")
            resp.raise_for_status()


def main():
    validate_env()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Fetching AI & tech news digest for {today}...")

    news = fetch_news()
    print(f"Got digest ({len(news)} chars). Sending to Telegram...")

    header = f"*Daily AI & Tech News* \u2014 {today}\n\n"
    send_telegram(header + news)

    print("Digest sent successfully.")


if __name__ == "__main__":
    main()
