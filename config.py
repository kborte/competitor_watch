"""Targets and settings for the competitor website watcher.

Only sites that are actually fetchable and permit it are here. Tawuniya and
QGIRCO both block automated fetches at the WAF/network layer (403 on
robots.txt itself, in Tawuniya's case) — that's not something to route
around with more aggressive scraping; track those two via the news layer
instead, not a direct crawler.
"""

import os

TARGETS = [
    {"company": "Bupa Arabia", "label": "estore (buy flow)", "url": "https://www.bupa.com.sa/en/estore"},
    {"company": "Bupa Arabia", "label": "homepage", "url": "https://www.bupa.com.sa/en/home"},
    {"company": "ADNIC", "label": "motor product page", "url": "https://adnic.ae/motor"},
    {"company": "ADNIC", "label": "homepage", "url": "https://adnic.ae/"},
    {"company": "Sukoon", "label": "car insurance page", "url": "https://www.sukoon.com/individuals/car-insurance"},
    {"company": "Sukoon", "label": "homepage", "url": "https://www.sukoon.com/"},
]

# Identify honestly rather than spoofing a browser — this is a legitimate,
# low-frequency monitor of public pages, not something to disguise.
USER_AGENT = "QIC-CompetitorWatch/1.0 (internal competitive-intelligence monitor)"
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SECONDS = 2  # be a good citizen between requests

STORE_PATH = os.path.join(os.path.dirname(__file__), "snapshots.json")

SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL")  # optional; only used with --post
