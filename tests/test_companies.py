"""The canonical company registry: one real competitor, many spellings.

Also pins the cross-file agreement that has no other enforcement — every crawler
keyword must resolve to a registry entry, or its findings silently land in the
market bucket.
"""

from backend import companies
from research_crawler import config as crawler_config


class TestCanonicalName:
    def test_known_alias_resolves_to_its_canonical_name(self):
        assert companies.canonical_name("Abu Dhabi National Insurance Company") == "ADNIC"

    def test_canonical_name_resolves_to_itself(self):
        for entry in companies.REGISTRY:
            assert companies.canonical_name(entry.canonical_name) == entry.canonical_name

    def test_unknown_company_falls_into_the_market_bucket(self):
        # Banks, ministries and regulators the market-wide keyword turns up.
        assert companies.canonical_name("Qatar National Bank") == companies.MARKET_BUCKET

    def test_retired_company_is_not_a_tracked_entity(self):
        assert companies.canonical_name("QLM") == companies.MARKET_BUCKET


class TestRegistryIntegrity:
    def test_canonical_name_is_always_among_its_own_aliases(self):
        for entry in companies.REGISTRY:
            assert entry.canonical_name in entry.aliases, entry.canonical_name

    def test_no_alias_is_claimed_by_two_companies(self):
        seen: dict[str, str] = {}
        for entry in companies.REGISTRY:
            for alias in entry.aliases:
                assert alias not in seen, f"{alias!r}: {seen.get(alias)} and {entry.canonical_name}"
                seen[alias] = entry.canonical_name

    def test_retired_aliases_are_not_also_registered(self):
        # A retired company must not resolve to a tracked entity, or it would
        # reappear on the dashboard.
        registered = set(companies.known_aliases())
        assert registered.isdisjoint(companies.RETIRED_ALIASES)

    def test_market_bucket_is_not_a_registry_entry(self):
        # It is an inverse set — "not any tracked competitor" — so treating it
        # as a finite alias list would silently return the wrong rows.
        assert companies.MARKET_BUCKET not in companies.known_aliases()


class TestCrossFileAgreement:
    def test_every_crawler_keyword_resolves_to_a_registry_entry(self):
        # Nothing enforces this at runtime: a keyword matching no alias does not
        # error, its findings just land in the market bucket instead of under
        # the company that was searched for.
        market = crawler_config.MARKET_WIDE_KEYWORD
        reference = crawler_config.QIC_REFERENCE_KEYWORD
        for keyword in crawler_config.KEYWORDS:
            if keyword in (market, reference):
                continue
            assert companies.canonical_name(keyword) != companies.MARKET_BUCKET, (
                f"keyword {keyword!r} is not an alias of any registry entry"
            )

    def test_market_wide_keyword_is_deliberately_not_a_company(self):
        assert companies.canonical_name(crawler_config.MARKET_WIDE_KEYWORD) \
            == companies.MARKET_BUCKET


class TestAliasLookup:
    def test_aliases_for_returns_every_spelling(self):
        aliases = companies.aliases_for("ADNIC")
        assert "ADNIC" in aliases
        assert "Abu Dhabi National Insurance Company" in aliases

    def test_aliases_for_unknown_input_returns_just_that_input(self):
        assert companies.aliases_for("Nonesuch Ltd") == ["Nonesuch Ltd"]

    def test_retired_aliases_is_a_list_for_sql_binding(self):
        # Bound as a SQL array; a tuple would not adapt the same way.
        assert isinstance(companies.retired_aliases(), list)
