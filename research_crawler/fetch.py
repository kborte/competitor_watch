"""Fetch a page and reduce it to clean text — adapted from the original
crawler's fetcher.py. Used here to independently verify a grounded search
result against the live page, rather than trusting the model's paraphrase
as the record. Also hangs onto the raw HTML so it can be stored as an
auditable snapshot of what the page looked like at observation time."""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

USER_AGENT = "QIC-CompetitorWatch/1.0 (internal competitive-intelligence monitor)"
CONTENT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "span"]
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


@dataclass
class FetchResult:
    final_url: str
    raw_html: str | None  # None if the response wasn't HTML, or exceeded MAX_SNAPSHOT_BYTES
    clean_text: str


def extract_clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    lines = []
    for el in soup.find_all(CONTENT_TAGS):
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if text and len(text) > 1 and (not lines or lines[-1] != text):
            lines.append(text)

    return "\n".join(lines)


def fetch_page(url: str, timeout: int = 15) -> FetchResult | None:
    """Returns FetchResult(final_url, raw_html, clean_text), or None if the fetch failed."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    content_type = resp.headers.get("Content-Type", "")
    raw_html = resp.text
    if "html" not in content_type.lower() or len(raw_html.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raw_html = None

    return FetchResult(final_url=resp.url, raw_html=raw_html, clean_text=extract_clean_text(resp.text))
