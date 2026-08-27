"""Canonical company registry — one real competitor, many spellings.

The LLM's `company` field drifts across crawls ("ADNIC" and "Abu Dhabi National
Insurance Company" both turn up for the same firm), so this maps every raw variant
seen to one canonical name. That lets /companies and /findings?company=... group
and filter correctly no matter which spelling a given crawl produced. Anything
unrecognized falls into the "Qatar Insurance Market" bucket.
"""

from dataclasses import dataclass


@dataclass
class CompanyEntry:
    """One real company and every raw string that should resolve to it."""

    canonical_name: str
    aliases: tuple[str, ...]  # includes canonical_name itself


# The canonical names here are EXACTLY the tracked competitors — the same list
# as research_crawler/config.py's KEYWORDS, minus its market-wide entry. Adding
# an entry adds a filter chip to the dashboard, so don't add one for a company
# that merely appears in an article (a partner bank, a regulator, an acquirer);
# those belong in the market bucket.
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
    # The one entry whose canonical name is NOT also its search keyword. The
    # crawler searches the full legal-ish form (a bare "Qatar General" is too
    # close to the market-wide keyword to search on), but the dashboard chip
    # reads better short — so the keyword lives in the alias list instead.
    CompanyEntry("Qatar General", (
        "Qatar General",
        "Qatar General Insurance & Reinsurance",
        "Qatar General Insurance and Reinsurance",
        "Qatar General Insurance & Reinsurance Company",
        "Qatar General Insurance and Reinsurance Company",
        "Qatar General Insurance & Reinsurance Co.",
        "Qatar General Insurance and Reinsurance Co.",
        "Qatar General Insurance and Reinsurance Company Q.P.S.C.",
        "Qatar General Insurance",
        "QGIRCO",
        "QGIRC",
    )),
]

_ALIAS_TO_CANONICAL = {alias: entry.canonical_name for entry in REGISTRY for alias in entry.aliases}
_CANONICAL_TO_ALIASES = {entry.canonical_name: list(entry.aliases) for entry in REGISTRY}


# Where every unregistered company string lands: banks, ministries and
# regulators the market-wide keyword turns up, and also any genuinely new
# competitor that appears before someone adds it to REGISTRY above.
MARKET_BUCKET = "Qatar Insurance Market"

# Companies deliberately dropped from tracking. Their findings stay in the
# database — the audit chain is the point of storing them — but the read API
# hides them. This must be an explicit list rather than "anything not in
# REGISTRY", because unregistered strings fall into MARKET_BUCKET, which
# legitimately holds banks and regulators; without it a retired competitor would
# silently inflate that bucket. Expect to keep adding: a retired company still
# turns up in market-wide results, and those are exempt from structure.py's
# company override, so the model invents fresh spelling variants.
RETIRED_ALIASES: tuple[str, ...] = (
    "QLM",
    "QLM Life & Medical Insurance",
    "QLM Life & Medical Insurance Company",
    "QLM Life & Medical Insurance Company QPSC",
    "QLM Life and Medical Insurance",
)


def canonical_name(raw_company: str) -> str:
    """Canonical display name for a raw company string, or MARKET_BUCKET if it
    is not a tracked competitor."""
    return _ALIAS_TO_CANONICAL.get(raw_company, MARKET_BUCKET)


def aliases_for(canonical_or_raw: str) -> list[str]:
    """Every raw string that should match this canonical name, or the input
    itself if unregistered. Not meaningful for MARKET_BUCKET — see known_aliases()."""
    return _CANONICAL_TO_ALIASES.get(canonical_or_raw, [canonical_or_raw])


def retired_aliases() -> list[str]:
    """Raw company strings the read API must hide."""
    # Safe when empty: `company != ALL('{}')` is vacuously true in SQL.
    return list(RETIRED_ALIASES)


def known_aliases() -> list[str]:
    """Every raw string belonging to some tracked competitor, for building the
    inverse "everything else" filter that defines MARKET_BUCKET."""
    return list(_ALIAS_TO_CANONICAL.keys())
