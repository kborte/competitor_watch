"""Reduces raw HTML to comparable plain text — mirrors research_crawler/
fetch.py's stripping logic so the backend can independently derive a dedup
signal from received source_html. Duplicated rather than imported, same as
schemas.py: crawler and backend agree on a wire format, not on code."""

import re

from bs4 import BeautifulSoup

CONTENT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "span"]


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
