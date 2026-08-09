"""Fetch a page and reduce it to clean text — adapted from the original
crawler's fetcher.py. Used here to independently verify a grounded search
result against the live page, rather than trusting the model's paraphrase
as the record. Also hangs onto the raw HTML so it can be stored as an
auditable snapshot of what the page looked like at observation time."""

import json
import re
from dataclasses import dataclass
from datetime import date as _date, timedelta as _timedelta

import requests
from bs4 import BeautifulSoup

_ISO_DATE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_TEXT_DATE_DMY = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
_TEXT_DATE_MDY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

USER_AGENT = "QIC-CompetitorWatch/1.0 (internal competitive-intelligence monitor)"
CONTENT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "td", "span"]
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


@dataclass
class FetchResult:
    final_url: str
    raw_html: str | None  # None if the response wasn't HTML, or exceeded MAX_SNAPSHOT_BYTES
    clean_text: str | None  # None if the destination resolved but content couldn't be fetched (e.g. 403)
    og_title: str | None = None
    og_image_url: str | None = None
    og_description: str | None = None
    og_site_name: str | None = None
    published_date: str | None = None


def _valid(year: int, month: int, day: int) -> str | None:
    """A publication date must be a real calendar date that has already
    happened — a future one means we picked up an events listing or an
    embargo stamp, not when the piece was published."""
    if not (2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        parsed = _date(year, month, day)
    except ValueError:  # e.g. 31 February
        return None
    # One day of slack absorbs timezone skew around "published just now".
    if parsed > _date.today() + _timedelta(days=1):
        return None
    return parsed.isoformat()


def _date_only(raw: str) -> str | None:
    """Normalizes the date formats that actually turn up in meta tags and
    JSON-LD — ISO timestamps, slash-separated dates, and the two common
    textual orderings — down to YYYY-MM-DD."""
    text = raw.strip()
    if not text:
        return None

    if match := _ISO_DATE.search(text):
        year, month, day = (int(g) for g in match.groups())
        if date := _valid(year, month, day):
            return date

    if match := _TEXT_DATE_DMY.search(text):  # "12 February 2026"
        day, month_name, year = match.groups()
        if month := _MONTHS.get(month_name[:3].lower()):
            if date := _valid(int(year), month, int(day)):
                return date

    if match := _TEXT_DATE_MDY.search(text):  # "February 12, 2026"
        month_name, day, year = match.groups()
        if month := _MONTHS.get(month_name[:3].lower()):
            if date := _valid(int(year), month, int(day)):
                return date

    return None


_META_DATE_PROPERTIES = (
    "article:published_time", "og:article:published_time", "og:published_time",
    "article:published", "og:pubdate",
)
_META_DATE_NAMES = (
    "date", "publish-date", "publishdate", "pubdate", "publication_date",
    "published_date", "article.published", "sailthru.date", "parsely-pub-date",
    "cxenseparse:recs:publishtime", "dc.date", "dc.date.issued", "dcterms.created",
)
# Deliberately excludes dateModified/og:updated_time — a "last modified"
# stamp is not when something was published, and on template-driven sites
# it's often just the last site-wide rebuild.
_JSONLD_DATE_KEYS = ("datePublished", "dateCreated", "uploadDate")

# A <time> tag only counts as the publish date when something about it
# says so — a bare <time> is just as likely to be an events sidebar or a
# "related articles" listing as the article's own byline.
_PUBLISH_HINT = re.compile(r"publish|posted|pubdate|byline|entry-date|article.?date", re.I)

# A date sitting in the URL path is a strong, extremely common signal on
# news sites (e.g. /news/2026/02/12/slug or /slug-2026-02-12).
_URL_DATE_PATTERNS = (
    re.compile(r"/(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[/-]|$)"),
    re.compile(r"[-_](\d{4})-(\d{2})-(\d{2})(?:[-_./]|$)"),
)


def extract_date_from_url(url: str) -> str | None:
    """Many news URLs embed the publish date in the path. Only accepts
    plausible calendar values, so an arbitrary numeric slug can't be
    misread as a date."""
    for pattern in _URL_DATE_PATTERNS:
        match = pattern.search(url)
        if not match:
            continue
        year, month, day = (int(g) for g in match.groups())
        if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _iter_jsonld_objects(data):
    """Yields every dict nested anywhere in a parsed JSON-LD blob —
    schema.org markup nests articles under @graph, arrays, mainEntity,
    etc., and the date can sit at any depth."""
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_jsonld_objects(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_objects(item)


def extract_published_date(html: str, url: str | None = None) -> str | None:
    """Deterministically pulls a publish date (YYYY-MM-DD) from structured
    markup — <meta> tags, JSON-LD, <time>, microdata, then the URL path —
    rather than asking the LLM to guess from stripped-down body text, where
    these dates never survive anyway (extract_clean_text() only reads
    visible content tags and actively strips <script>, which is exactly
    where JSON-LD lives)."""
    soup = BeautifulSoup(html, "html.parser")

    for prop in _META_DATE_PROPERTIES:
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            if date := _date_only(tag["content"]):
                return date

    for name in _META_DATE_NAMES:
        # Case-insensitive: DC.date / dc.date / DC.Date all occur in the wild.
        tag = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(name)}$", re.I)})
        if tag and tag.get("content"):
            if date := _date_only(tag["content"]):
                return date

    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        for obj in _iter_jsonld_objects(data):
            for key in _JSONLD_DATE_KEYS:
                if obj.get(key):
                    if date := _date_only(str(obj[key])):
                        return date

    for attrs in ({"itemprop": "datePublished"}, {"itemprop": "dateCreated"}):
        tag = soup.find(attrs=attrs)
        if tag:
            raw = tag.get("content") or tag.get("datetime") or tag.get_text(" ", strip=True)
            if raw and (date := _date_only(raw)):
                return date

    # Only <time> tags that identify themselves as publication dates. A
    # bare <time> is just as often an events sidebar or a related-articles
    # listing (confirmed in the wild: one source's first <time> was an
    # upcoming-conference date months in the future).
    for time_tag in soup.find_all("time", attrs={"datetime": True}):
        signals = " ".join(filter(None, [
            " ".join(time_tag.get("class", [])), time_tag.get("itemprop", ""),
            time_tag.get("pubdate", ""), time_tag.get("id", ""),
            " ".join(filter(None, [p.get("class") and " ".join(p["class"]) for p in time_tag.parents
                                    if getattr(p, "get", None)][:2])),
        ]))
        if _PUBLISH_HINT.search(signals) and (date := _date_only(time_tag["datetime"])):
            return date

    return extract_date_from_url(url) if url else None


def extract_og_metadata(html: str) -> dict[str, str | None]:
    """Pulls Open Graph (falling back to Twitter Card) meta tags for a
    Messenger-style link-preview card — reuses the same fetched HTML
    already in hand for source_html/clean_text, no extra network call."""
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
            content = tag.get("content") if tag else None
            if content and content.strip():
                return content.strip()
        return None

    return {
        "og_title": meta("og:title", "twitter:title"),
        "og_image_url": meta("og:image", "twitter:image"),
        "og_description": meta("og:description", "twitter:description"),
        "og_site_name": meta("og:site_name"),
    }


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
    """Returns FetchResult(final_url, raw_html, clean_text), or None only
    when the destination couldn't be resolved at all (DNS/timeout/connection
    error) — there's no final_url to report in that case. A request that
    resolves (redirects followed) but comes back with a bad status (403,
    404, ...) still returns a FetchResult with the real resolved final_url,
    just with raw_html/clean_text left None — the caller can still cite the
    real page, it just can't independently verify its content."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException:
        return None

    try:
        resp.raise_for_status()
    except requests.RequestException:
        return FetchResult(final_url=resp.url, raw_html=None, clean_text=None)

    content_type = resp.headers.get("Content-Type", "")
    is_html = "html" in content_type.lower()
    raw_html = resp.text
    if not is_html or len(raw_html.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raw_html = None
    og = extract_og_metadata(resp.text) if is_html else {}
    published_date = (
        extract_published_date(resp.text, resp.url) if is_html
        else extract_date_from_url(resp.url)
    )

    return FetchResult(
        final_url=resp.url, raw_html=raw_html, clean_text=extract_clean_text(resp.text),
        og_title=og.get("og_title"), og_image_url=og.get("og_image_url"),
        og_description=og.get("og_description"), og_site_name=og.get("og_site_name"),
        published_date=published_date,
    )
