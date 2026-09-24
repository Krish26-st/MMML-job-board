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

REMOTE_KEYWORDS = ["remote", "work from home", "wfh", "distributed team", "anywhere"]

# If a listing says "remote" but also names a specific non-India region, it's
# very likely remote-within-that-region rather than open to India — treat it
# as excluded rather than blindly matching on the word "remote" alone.
EXCLUDED_REMOTE_REGIONS = [
    "united states", "usa", " us ", "us only", "uk", "united kingdom",
    "canada", "germany", "france", "singapore", "australia", "ireland",
    "spain", "netherlands", "emea", "americas", "latam", "japan", "china",
]

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
    padded = f" {location.lower()} "
    if not any(k in padded for k in REMOTE_KEYWORDS):
        return False
    return not any(r in padded for r in EXCLUDED_REMOTE_REGIONS)


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
