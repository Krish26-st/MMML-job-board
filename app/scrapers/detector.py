import re
from urllib.parse import urlparse

# Any location string containing one of these is treated as an India posting.
# Extend this list as new office cities come up in practice.
INDIA_KEYWORDS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "gurgaon",
    "gurugram", "pune", "hyderabad", "chennai", "noida", "kolkata", "ahmedabad",
    "navi mumbai", "thane", "coimbatore", "jaipur",
]


def detect_source_type(url: str) -> str:
    """Dynamically classifies a careers URL. Greenhouse, Lever, Workday, and
    Ashby all expose a structured JSON API keyed off the URL, so they each
    get a dedicated fast path with no browser involved. Everything else
    falls back to the Playwright custom scraper -- which is now truly the
    last resort, reserved for boards with no known public API (in-house
    boards, Oracle HCM, Skima, etc.), keeping load on Chromium to a minimum.
    """
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "myworkdayjobs.com" in host:
        return "workday"
    if "ashbyhq.com" in host:
        return "ashby"
    return "custom"


def extract_greenhouse_token(url: str) -> str | None:
    # e.g. https://boards.greenhouse.io/stripe  or
    #      https://job-boards.greenhouse.io/stripe/jobs/12345
    m = re.search(r"greenhouse\.io/([a-zA-Z0-9\-_]+)", url)
    return m.group(1) if m else None


def extract_lever_site(url: str) -> str | None:
    # e.g. https://jobs.lever.co/zerodha
    m = re.search(r"lever\.co/([a-zA-Z0-9\-_]+)", url)
    return m.group(1) if m else None


_LOCALE_RE = re.compile(r"^[a-zA-Z]{2}-[a-zA-Z]{2}$")


def extract_workday_parts(url: str) -> dict | None:
    """e.g. https://lseg.wd3.myworkdayjobs.com/Careers?locationCountry=...
    -> {"tenant": "lseg", "host": "lseg.wd3.myworkdayjobs.com", "site": "Careers"}

    or     https://yelp.myworkdayjobs.com/Yelp   (no wd# cluster subdomain --
    some smaller tenants are hosted this way)
    -> {"tenant": "yelp", "host": "yelp.myworkdayjobs.com", "site": "Yelp"}

    Rather than assume a fixed number of subdomain parts, this just checks
    "myworkdayjobs" appears in the host and uses the host exactly as given
    to build the API URL -- so it works whether or not a cluster subdomain
    is present.
    """
    parsed = urlparse(url)
    host = parsed.netloc
    host_parts = host.split(".")
    if "myworkdayjobs" not in host or len(host_parts) < 3:
        return None
    tenant = host_parts[0]

    path_parts = [p for p in parsed.path.split("/") if p]
    site = next((p for p in path_parts if not _LOCALE_RE.match(p)), None)
    if not tenant or not site:
        return None
    return {"tenant": tenant, "host": host, "site": site}


def extract_ashby_board_name(url: str) -> str | None:
    # e.g. https://jobs.ashbyhq.com/openai -> "openai"
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    return path_parts[0] if path_parts else None


def is_india_location(loc: str | None) -> bool:
    if not loc:
        return False
    low = loc.lower()
    return any(k in low for k in INDIA_KEYWORDS)
