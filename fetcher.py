"""Fetch a page and reduce it to a stable, line-per-content-element text
snapshot — stripped of scripts/styles, deduped of repeated nested-tag text,
so a diff between two snapshots reflects real content changes rather than
markup noise."""

import re

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, USER_AGENT

CONTENT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "span", "button", "a"]


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    lines = []
    for el in soup.find_all(CONTENT_TAGS):
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if text and len(text) > 1 and (not lines or lines[-1] != text):
            lines.append(text)

    return "\n".join(lines)
