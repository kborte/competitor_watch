"""The freshness rule — the least obvious logic in the system.

A finding is dated by its source's own publish date where one exists, and may
fall back to crawl time only for categories where being undated is normal. These
tests pin both halves, plus the SQL rendering that used to be written out three
times in two parameter styles.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.reads import windows


class TestBounds:
    @pytest.mark.parametrize("window,days", [("week", 7), ("month", 30), ("year", 365)])
    def test_rolling_windows_look_back_the_right_distance(self, window, days):
        retrieved, published = windows.bounds(window)
        now = datetime.now(UTC)
        assert abs((now - retrieved) - timedelta(days=days)) < timedelta(seconds=5)
        assert published is not None

    def test_all_has_no_cutoff(self):
        assert windows.bounds("all") == (None, None)

    def test_unknown_window_is_treated_as_no_cutoff(self):
        # Reached only if a caller bypasses main.py's Literal validation; it
        # must not raise.
        assert windows.bounds("nonsense") == (None, None)

    def test_today_is_a_qatar_local_day(self):
        retrieved, published = windows.bounds("today")
        qatar_now = datetime.now(UTC) + windows.QATAR_OFFSET
        # The cutoff is Qatar midnight expressed in UTC, so it is never ahead of
        # now and never more than 24h behind.
        assert retrieved <= datetime.now(UTC)
        assert datetime.now(UTC) - retrieved < timedelta(days=1)
        assert published == qatar_now.date()


class TestCrawlRecencyCategories:
    def test_evergreen_categories_may_use_crawl_time(self):
        # A competitor's own product page carries no publish date, so "we first
        # saw this change today" genuinely is the news.
        for category in ("product", "marketing", "social_sentiment", "other"):
            assert category in windows.CRAWL_RECENCY_CATEGORIES

    def test_dated_categories_may_not(self):
        # A real article always has a publish date, so a missing one means
        # extraction failed. Letting crawl time stand in is what once put 2019
        # articles in the "this week" view.
        for category in ("news", "regulatory", "financial_results",
                         "investment_or_acquisition"):
            assert category not in windows.CRAWL_RECENCY_CATEGORIES


class TestFreshnessSql:
    def test_placeholder_count_matches_param_count(self):
        sql = windows.freshness_sql()
        params = windows.freshness_params("week")
        assert sql.count("%s") == len(params) == 3

    def test_prior_placeholder_count_matches_param_count(self):
        sql = windows.prior_sql()
        params = windows.prior_params("week")
        assert sql.count("%s") == len(params) == 5

    def test_params_are_none_when_the_window_has_no_cutoff(self):
        assert windows.freshness_params("all") is None
        assert windows.prior_params("all") is None

    def test_alias_is_applied_to_every_column_reference(self):
        sql = windows.freshness_sql("x")
        assert "x.published_at" in sql and "x.retrieved_at" in sql and "x.category" in sql
        assert "f.published_at" not in sql

    def test_named_rendering_matches_the_positional_one(self):
        # One rule, two renderings: if these ever diverge, a KPI and the feed
        # can disagree about what "this week" means.
        positional = windows.freshness_sql("t")
        named = windows.freshness_sql_named("week", "t")
        assert named.replace("%(week_date)s", "%s") \
                    .replace("%(crawl_recency_cats)s", "%s") \
                    .replace("%(week_instant)s", "%s") == positional

    def test_prior_period_is_bounded_on_both_sides(self):
        # Open-ended, consecutive periods would overlap and double-count.
        assert windows.prior_sql().count("<") == 2

    def test_prior_period_ends_where_the_current_one_begins(self):
        current = windows.freshness_params("week")
        prior = windows.prior_params("week")
        # Dates line up exactly.
        assert prior[1] == current[0]
        # Instants are within microseconds rather than identical: each call
        # reads the clock independently, so the two boundaries are computed a
        # few microseconds apart. A finding retrieved inside that sliver would
        # fall in neither period — theoretically a gap, practically never, and
        # not worth threading a clock through the API to close.
        assert abs(prior[4] - current[2]) < timedelta(milliseconds=10)

    def test_today_prior_period_is_one_day_not_seven(self):
        current = windows.freshness_params("today")
        prior = windows.prior_params("today")
        assert (current[0] - prior[0]).days == 1
