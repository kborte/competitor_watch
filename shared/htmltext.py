"""Reduce HTML to comparable plain text.

Used on both sides of the wire, and the results must agree: the crawler derives
the text it sends, the backend derives a content hash from the snapshot it
receives, and dedup compares hashes across runs. Two implementations would make
"did this page change?" depend on which side looked.
"""

import re

from bs4 import BeautifulSoup

CONTENT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "span"]


def extract_clean_text(html: str) -> str:
    """Flattens HTML to one line of visible text per content element, dropping
    scripts, styles and consecutive duplicates."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    lines = []
    for el in soup.find_all(CONTENT_TAGS):
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if text and len(text) > 1 and (not lines or lines[-1] != text):
            lines.append(text)

    return "\n".join(lines)
