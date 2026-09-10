"""The novelty decision — the only place "is this new?" is answered, and the
mechanism that keeps LLM spend proportional to real news.

`check()` needs a database, so these tests drive it through a tiny stub that
records what it was asked. The URL normalisation and hashing beneath it are pure.
"""

import pytest

from backend import dedup


class FakeLedger:
    """Stands in for db.get_seen_url — returns whatever the test seeded."""

    def __init__(self, seen=None):
        self.seen = seen or {}
        self.queries = []

    def get_seen_url(self, conn, url, scope):
        self.queries.append((url, scope))
        return self.seen.get((url, scope))


class Finding:
    def __init__(self, url, category="news", html=None, is_reference=False):
        self.source_url = url
        self.category = category
        self.source_html = html
        self.is_reference = is_reference


@pytest.fixture
def ledger(monkeypatch):
    fake = FakeLedger()
    monkeypatch.setattr(dedup.db, "get_seen_url", fake.get_seen_url)
    return fake


class TestNormalizeUrl:
    @pytest.mark.parametrize("raw,expected", [
        ("https://x.test/a/", "https://x.test/a"),
        ("https://x.test/a", "https://x.test/a"),
        ("https://x.test/a?utm_source=news", "https://x.test/a"),
        ("https://x.test/a#section", "https://x.test/a"),
        ("HTTPS://X.TEST/a", "https://x.test/a"),
        ("https://x.test", "https://x.test/"),
    ])
    def test_trivial_variants_collapse_to_one_entry(self, raw, expected):
        assert dedup.normalize_url(raw) == expected

    def test_path_case_is_preserved(self):
        # Host is case-insensitive, path is not: /News and /news can be
        # different pages.
        assert dedup.normalize_url("https://x.test/News") == "https://x.test/News"


class TestCheck:
    def test_unseen_url_is_always_new(self, ledger):
        needs, _hash = dedup.check(None, Finding("https://x.test/new"))
        assert needs is True

    def test_seen_article_is_a_duplicate(self, ledger):
        # A published article is written once and not meaningfully rewritten.
        ledger.seen[("https://x.test/a", "competitor")] = ("news", "somehash")
        needs, _hash = dedup.check(None, Finding("https://x.test/a", "news"))
        assert needs is False

    @pytest.mark.parametrize("category", ["product", "marketing"])
    def test_unchanged_stable_page_is_a_duplicate(self, ledger, category):
        html = "<html><body><p>Same offer</p></body></html>"
        content_hash = dedup._content_hash(Finding("u", html=html))
        ledger.seen[("https://x.test/p", "competitor")] = (category, content_hash)
        needs, _hash = dedup.check(None, Finding("https://x.test/p", category, html=html))
        assert needs is False

    @pytest.mark.parametrize("category", ["product", "marketing"])
    def test_edited_stable_page_is_new_again(self, ledger, category):
        old_hash = dedup._content_hash(Finding("u", html="<p>Old price</p>"))
        ledger.seen[("https://x.test/p", "competitor")] = (category, old_hash)
        needs, _hash = dedup.check(
            None, Finding("https://x.test/p", category, html="<p>New price</p>"),
        )
        # A changed hash on a competitor's own page is exactly the signal this
        # system exists to catch.
        assert needs is True

    def test_missing_snapshot_is_retried_rather_than_guessed(self, ledger):
        ledger.seen[("https://x.test/p", "competitor")] = ("product", "somehash")
        needs, content_hash = dedup.check(None, Finding("https://x.test/p", "product", html=None))
        assert needs is True
        assert content_hash is None

    def test_reference_findings_use_a_separate_ledger_scope(self, ledger):
        # QIC is tracked as a benchmark; its sightings must not mark a URL seen
        # for the competitor feed, or vice versa.
        dedup.check(None, Finding("https://x.test/q", is_reference=True))
        assert ledger.queries == [("https://x.test/q", "reference")]

    def test_a_url_seen_only_as_reference_is_still_new_as_competitor(self, ledger):
        ledger.seen[("https://x.test/q", "reference")] = ("news", "h")
        needs, _hash = dedup.check(None, Finding("https://x.test/q", is_reference=False))
        assert needs is True


class TestContentHash:
    def test_hash_ignores_markup_that_does_not_change_visible_text(self):
        a = dedup._content_hash(Finding("u", html="<p>Hello</p>"))
        b = dedup._content_hash(Finding("u", html="<div><p>Hello</p></div>"))
        assert a == b

    def test_hash_ignores_scripts(self):
        # Analytics and ad tags change on every load; they must not read as a
        # content change.
        a = dedup._content_hash(Finding("u", html="<p>Hi</p>"))
        b = dedup._content_hash(Finding("u", html="<p>Hi</p><script>x=1</script>"))
        assert a == b

    def test_hash_tracks_visible_text(self):
        a = dedup._content_hash(Finding("u", html="<p>Hello</p>"))
        b = dedup._content_hash(Finding("u", html="<p>Goodbye</p>"))
        assert a != b

    def test_no_html_means_no_hash(self):
        assert dedup._content_hash(Finding("u", html=None)) is None
