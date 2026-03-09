"""Price Monitor

Monitors product pages for price changes and prints alerts.
Configure URLs via MONITOR_URLS env var (comma-separated) or edit the defaults below.
"""

import os
import re
import json
import urllib.request
from datetime import datetime, timezone

PRICE_PATTERN = re.compile(r'\$[\d,]+\.?\d{0,2}')
DEFAULT_URLS = [
    "https://httpbin.org/html",  # placeholder — replace with real product URLs
]


def get_urls() -> list[str]:
    env_urls = os.environ.get("MONITOR_URLS", "")
    if env_urls.strip():
        return [u.strip() for u in env_urls.split(",") if u.strip()]
    return DEFAULT_URLS


def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "BerthPriceMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_prices(html: str) -> list[str]:
    return PRICE_PATTERN.findall(html)


def parse_price(price_str: str) -> float:
    return float(price_str.replace("$", "").replace(",", ""))


def main():
    threshold = float(os.environ.get("PRICE_THRESHOLD", "50.00"))
    urls = get_urls()

    print(f"Price Monitor — checking {len(urls)} URL(s), threshold: ${threshold:.2f}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}\n")

    results = []
    for url in urls:
        print(f"Checking: {url}")
        try:
            html = fetch_page(url)
            prices = extract_prices(html)
            if prices:
                lowest = min(parse_price(p) for p in prices)
                status = "ALERT" if lowest < threshold else "OK"
                print(f"  Found {len(prices)} price(s), lowest: ${lowest:.2f} [{status}]")
                results.append({"url": url, "prices": prices, "lowest": lowest, "status": status})
            else:
                print("  No prices found on page")
                results.append({"url": url, "prices": [], "lowest": None, "status": "NO_PRICES"})
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"url": url, "error": str(e), "status": "ERROR"})

    # Save results
    output = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "results": results,
    }
    with open("price_report.json", "w") as f:
        json.dump(output, f, indent=2)

    alerts = [r for r in results if r.get("status") == "ALERT"]
    print(f"\nDone. {len(alerts)} alert(s) found. Report saved to price_report.json")


if __name__ == "__main__":
    main()
