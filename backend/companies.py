"""Canonical company registry — the LLM's normalized `company` field on
Finding drifts in spelling/format across crawls (e.g. "ADNIC" vs "Abu Dhabi
National Insurance Company" are the same real company; confirmed by seeing
both show up independently in real crawl data). This registry maps each of
the tracked real competitors to every raw string variant seen for it, so
/companies and /findings?company=... can group/filter correctly regardless
of which spelling a given crawl happened to produce.

The canonical names here are EXACTLY the tracked competitors — the same
list as research_crawler/config.py's KEYWORDS, minus its market-wide
entry. Nothing else is ever its own entity. Adding a canonical entry here
adds a filter chip to the dashboard, so don't add one for a company that
merely appears in an article (a partner bank, a regulator, an acquirer);
those belong in the market bucket.

Any raw `company` string NOT listed here — a bank, a ministry, a
regulator, or anything else that isn't a tracked competitor, most often
produced by the market-wide search keyword — falls back to "Qatar
Insurance Market" rather than getting its own chip. The trade-off: a
genuinely new competitor appearing before someone adds it here also lands
in that bucket until the registry is updated."""

from dataclasses import dataclass


@dataclass
class CompanyEntry:
    canonical_name: str
    aliases: tuple[str, ...]  # includes canonical_name itself


REGISTRY: list[CompanyEntry] = [
    CompanyEntry("Bupa Arabia", (
        "Bupa Arabia",
        "Bupa Global",  # Bupa's international arm — folded in, not tracked separately
    )),
    CompanyEntry("Tawuniya", (
        "Tawuniya",
        "The Cooperative Insurance Company",
        "The Cooperative Insurance Company (Tawuniya)",
    )),
    CompanyEntry("ADNIC", (
        "ADNIC",
        "Abu Dhabi National Insurance Company",
    )),
    CompanyEntry("Sukoon Insurance", (
        "Sukoon Insurance",
        "Sukoon",
    )),
    CompanyEntry("Alkhaleej Takaful", (
        "Alkhaleej Takaful",
        "Alkhaleej Takaful Insurance",
        "Alkhaleej Takaful Insurance Company",
        "Al Khaleej Takaful Insurance Company Q.P.S.C.",
        "AKTI",
    )),
    CompanyEntry("Beema", (
        "Beema",
        "Beema (Damaan Islamic Insurance Company Q.P.S.C., Qatar)",
        "Damaan Islamic Insurance Company",
        "Damaan Islamic Insurance Company (Beema)",
    )),
    CompanyEntry("Doha Insurance", (
        "Doha Insurance",
        "Doha Insurance Group",
    )),
    CompanyEntry("QIIC", (
        "QIIC",
        "Qatar Islamic Insurance Group",
        "Qatar Islamic Insurance Company",
        "Qatar Islamic Insurance",
    )),
]

_ALIAS_TO_CANONICAL = {alias: entry.canonical_name for entry in REGISTRY for alias in entry.aliases}
_CANONICAL_TO_ALIASES = {entry.canonical_name: list(entry.aliases) for entry in REGISTRY}


MARKET_BUCKET = "Qatar Insurance Market"

# Companies deliberately dropped from tracking. Their findings stay in the
# database — the audit chain is the point of storing them, and deleting would
# cascade through llm_calls and changes — but the read API filters them out.
# This has to be an explicit list rather than "anything not in REGISTRY":
# canonical_name() sends every unregistered string to MARKET_BUCKET, and that
# bucket legitimately holds banks, ministries and regulators the market-wide
# keyword turns up. Without this list a retired competitor's findings would
# silently inflate the market bucket, indistinguishable from real market news.
# Spelling drift applies here exactly as it does to REGISTRY: the market-wide
# keyword is exempt from structure.py's company override, so the model is free
# to invent variants ("... and Medical" vs "... & Medical"). A retired company
# will keep turning up in market-wide results, so expect to add to this list.
RETIRED_ALIASES: tuple[str, ...] = (
    "QLM",
    "QLM Life & Medical Insurance",
    "QLM Life & Medical Insurance Company",
    "QLM Life & Medical Insurance Company QPSC",
    "QLM Life and Medical Insurance",
)


def canonical_name(raw_company: str) -> str:
    """Canonical display name for a raw company string, or MARKET_BUCKET
    if it's not a known tracked competitor at all."""
    return _ALIAS_TO_CANONICAL.get(raw_company, MARKET_BUCKET)


def aliases_for(canonical_or_raw: str) -> list[str]:
    """Every raw string variant that should match this canonical name, or
    just the input itself if it's not a registry entry. Not meaningful for
    MARKET_BUCKET — that's an inverse set (see known_aliases()), not a
    finite alias list, since it covers whatever ISN'T a tracked
    competitor."""
    return _CANONICAL_TO_ALIASES.get(canonical_or_raw, [canonical_or_raw])


def retired_aliases() -> list[str]:
    """Raw company strings the read API must hide (see RETIRED_ALIASES). An
    empty list is safe in SQL — `company != ALL('{}')` is vacuously true, so
    nothing gets filtered when nothing is retired."""
    return list(RETIRED_ALIASES)


def known_aliases() -> list[str]:
    """Every raw string recognized as belonging to some tracked
    competitor — used to build the inverse "everything else" filter for
    MARKET_BUCKET (a company filter for the bucket means "not any of
    these", not "matches one of these")."""
    return list(_ALIAS_TO_CANONICAL.keys())
