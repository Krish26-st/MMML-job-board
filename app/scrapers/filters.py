"""Two strict filters applied uniformly to every job, regardless of which
handler fetched it (Greenhouse, Lever, Workday, Ashby, or the custom
Playwright scraper). Keeping this in one place means every ATS integration
obeys the same rules and behaves consistently as new ones get added.

  FILTER 1 - location: the job must be based in India, OR be a remote role.
  FILTER 2 - relevance: the job must be finance / finance-adjacent.

Both are heuristic keyword matches over whatever text the source gives us
(title, location string, department/team/category if available). They're
intentionally kept in one small module so the keyword lists are easy to
tune without touching any scraper's fetch logic.
"""
import re
from .detector import is_india_location

REMOTE_KEYWORDS = [
    "remote", "work from home", "wfh", "distributed team", "anywhere",
    "fully remote", "100% remote", "work remotely",
]

# Words stripped out before checking whether anything *specific* is left in
# a "remote" location string. This replaces a fixed blacklist of country
# names (which broke on any new phrasing -- "Remote (US)", "Remote NA",
# "Remote - APAC" all slipped through a literal "united states" / " us "
# style list). Instead: strip every generic/remote/employment-type word,
# and if a specific place name is still sitting there afterwards (a
# country, a region code, a city), treat it as NOT genuinely open remote
# work -- only reject-free, no-region-attached "remote" listings pass.
_REMOTE_NOISE_WORDS = {
    "remote", "work", "from", "home", "wfh", "distributed", "team",
    "anywhere", "fully", "100", "remotely", "only", "based", "eligible",
    "role", "position", "job", "in", "the", "for", "candidates", "hybrid",
    "office", "or", "and", "location", "flexible",
    "worldwide", "global", "international",  # explicitly unrestricted
    "full", "time", "part", "contract", "permanent", "temporary",       # employment type, not geography
}


def _leftover_after_stripping_remote_noise(location: str) -> str:
    # Normalize punctuation to spaces first so "(US)" / "US," / "US)"
    # behave the same as " US " -- the old blacklist approach broke
    # specifically because it required exact space-padding.
    cleaned = re.sub(r"[^a-z0-9]+", " ", location.lower())
    tokens = [t for t in cleaned.split() if t not in _REMOTE_NOISE_WORDS]
    return " ".join(tokens).strip()

FINANCE_KEYWORDS = [
    "financ", "accounting", "accountant", "treasury", "taxation", " tax ",
    "audit", "invest", "trading", "trader", "equity research", "risk",
    "compliance", "banking", "banker", "fund ", "wealth", "actuar",
    "fp&a", "controller", "credit", "underwrit", "portfolio",
    "asset management", "private equity", "hedge fund", "mutual fund",
    "corporate finance", "bookkeep", "payroll", "quant", "valuation",
    "mergers", "m&a", "capital markets", "brokerage", "custody",
    "kyc", "aml", " fx ", "forex", "securities", "derivatives",
    "fixed income", "financial analyst", "financial planning",
    "revenue accountant", "billing", "collections",
]

_FINANCE_PATTERN = re.compile("|".join(re.escape(k) for k in FINANCE_KEYWORDS), re.I)


def is_remote(location: str | None) -> bool:
    if not location:
        return False
    low = location.lower()
    if not any(k in f" {low} " for k in REMOTE_KEYWORDS):
        return False
    # "remote" was mentioned -- now make sure nothing specific rides along
    # with it (a country, "NA", "APAC", a city, etc). Only a genuinely
    # unrestricted remote listing (or one that explicitly says India,
    # already handled by is_india_location before this ever runs) passes.
    leftover = _leftover_after_stripping_remote_noise(low)
    return leftover == ""


def passes_location_filter(location: str | None) -> bool:
    """FILTER 1: India-based OR remote."""
    return is_india_location(location) or is_remote(location)


def is_finance_related(*texts: str | None) -> bool:
    """FILTER 2: title/department/team text mentions a finance-related term."""
    combined = " ".join(t for t in texts if t)
    if not combined:
        return False
    return bool(_FINANCE_PATTERN.search(combined))


def passes_all_filters(title: str | None, location: str | None, department: str | None = None) -> bool:
    return passes_location_filter(location) and is_finance_related(title, department)
