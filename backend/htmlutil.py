"""HTML helpers for the backend.

extract_clean_text() reduces raw HTML to comparable plain text so dedup can derive
a content hash from a received snapshot; inject_base_href() prepares a stored
snapshot for display. The extraction mirrors research_crawler/fetch.py and is
duplicated rather than imported, same as schemas.py: the crawler is deployed
separately, so the two agree on a wire format, not on code.
"""

import re
from html import escape

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


def inject_base_href(html: str, base_url: str) -> str:
    """Inserts a <base> tag so relative asset paths in a captured snapshot resolve
    against the original site instead of 404ing against our own backend."""
    base_tag = f'<base href="{escape(base_url)}">'
    lower = html.lower()
    head_idx = lower.find("<head")
    if head_idx == -1:
        return base_tag + html
    insert_at = lower.find(">", head_idx) + 1
    return html[:insert_at] + base_tag + html[insert_at:]
