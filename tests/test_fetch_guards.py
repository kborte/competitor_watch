"""The fetch layer's guards and extractors.

The URL guard matters more now the crawler runs inside a cluster: a request to a
link-local or RFC1918 address reaches things a public runner never could. The
date extractor is here because getting it wrong is what once put articles from
previous years in the "this week" view.
"""

import pytest

from research_crawler import fetch


class TestUrlGuard:
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "gopher://example.com/1",
        "ftp://example.com/x",
        "data:text/html,<h1>x</h1>",
    ])
    def test_non_http_schemes_are_refused(self, url):
        assert fetch._check_url(url) is not None

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://169.254.169.254/latest/meta-data/",   # cloud metadata endpoint
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://172.16.0.1/x",
        "http://[::1]/x",
    ])
    def test_private_and_loopback_addresses_are_refused(self, url):
        assert fetch._check_url(url) is not None

    def test_url_without_a_host_is_refused(self):
        assert fetch._check_url("http:///nohost") is not None

    def test_ordinary_public_url_is_allowed(self):
        assert fetch._check_url("https://example.com/article") is None


class TestExtractDateFromUrl:
    @pytest.mark.parametrize("url,expected", [
        ("https://x.test/news/2026/02/12/slug", "2026-02-12"),
        ("https://x.test/news/2026-02-12/slug", "2026-02-12"),
        ("https://x.test/slug-2026-02-12", "2026-02-12"),
        ("https://x.test/2026/2/9/slug", "2026-02-09"),
    ])
    def test_dates_in_the_path_are_recognised(self, url, expected):
        assert fetch.extract_date_from_url(url) == expected

    @pytest.mark.parametrize("url", [
        "https://x.test/product/12345678",
        "https://x.test/article/9999/99/99",
        "https://x.test/offers",
    ])
    def test_arbitrary_numbers_are_not_read_as_dates(self, url):
        assert fetch.extract_date_from_url(url) is None


class TestValidDate:
    def test_impossible_calendar_dates_are_rejected(self):
        assert fetch._valid(2026, 2, 31) is None
        assert fetch._valid(2026, 13, 1) is None

    def test_future_dates_are_rejected(self):
        # A future date means an events listing or an embargo stamp, not a
        # publication date.
        assert fetch._valid(2099, 1, 1) is None

    def test_a_real_past_date_is_accepted(self):
        assert fetch._valid(2026, 2, 12) == "2026-02-12"


class TestExtractPublishedDate:
    def test_meta_property_is_used(self):
        html = '<html><head><meta property="article:published_time" content="2026-02-12T09:00:00Z"></head></html>'
        assert fetch.extract_published_date(html) == "2026-02-12"

    def test_json_ld_is_used_at_any_depth(self):
        html = '''<html><head><script type="application/ld+json">
        {"@graph":[{"@type":"Article","datePublished":"2026-02-12"}]}
        </script></head></html>'''
        assert fetch.extract_published_date(html) == "2026-02-12"

    def test_last_modified_is_not_treated_as_published(self):
        # On template-driven sites a "modified" stamp is often just the last
        # site-wide rebuild.
        html = '<html><head><meta property="og:updated_time" content="2026-02-12"></head></html>'
        assert fetch.extract_published_date(html) is None

    def test_bare_time_tag_is_ignored(self):
        # Confirmed in the wild: one source's first <time> was an upcoming
        # conference months in the future.
        html = '<html><body><time datetime="2026-02-12">Feb 12</time></body></html>'
        assert fetch.extract_published_date(html) is None

    def test_time_tag_that_identifies_itself_is_used(self):
        html = '<html><body><time class="entry-date published" datetime="2026-02-12">x</time></body></html>'
        assert fetch.extract_published_date(html) == "2026-02-12"

    def test_url_path_is_the_last_resort(self):
        assert fetch.extract_published_date("<html></html>", "https://x.test/2026/02/12/a") \
            == "2026-02-12"


class TestExtractCleanText:
    def test_scripts_and_styles_are_stripped(self):
        html = "<p>Real</p><script>var x=1</script><style>p{}</style>"
        assert fetch.extract_clean_text(html) == "Real"

    def test_consecutive_duplicates_are_collapsed(self):
        assert fetch.extract_clean_text("<p>Same</p><p>Same</p>") == "Same"

    def test_whitespace_is_normalised(self):
        assert fetch.extract_clean_text("<p>a\n\n   b</p>") == "a b"
