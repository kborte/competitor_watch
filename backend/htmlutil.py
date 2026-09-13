"""HTML helpers for the backend.

extract_clean_text() is re-exported from shared/ — dedup derives a content hash
from it, and that hash must match what the crawler would compute from the same
page. inject_base_href() is backend-only: it prepares a stored snapshot for
display.
"""

from html import escape

from shared.htmltext import extract_clean_text

__all__ = ["extract_clean_text", "inject_base_href"]


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
