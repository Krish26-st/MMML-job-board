"""Last-resort scraper for career sites with no known public API (Oracle
HCM, Skima, in-house boards like TCS, etc.), driven by a single headless
Chromium tab via Playwright. Greenhouse, Lever, Workday, and Ashby all now
have dedicated API-based handlers (see greenhouse.py / lever.py /
workday.py / ashby.py), so this module — the expensive one — only runs for
everything else, which keeps Chromium load to a minimum.

Beyond a job count, this also tries to extract the actual list of postings
(title, location, department, URL) so the job board can show real listings,
not just a number. Three independent signals are gathered for the count and
reconciled into one number, used as a fallback when individual postings
can't be extracted:

  1. TEXT MATCH   - regex over the rendered page text for phrases like
                     "3,241 jobs found" / "Jobs: 128". This is what broke for
                     JPMorgan (it reports the GLOBAL total, not India), so it
                     is deliberately the least-trusted signal below.
  2. CARD COUNT    - counts DOM elements matching common job-card selectors
                     (the repeating element each posting renders as).
  3. ID COUNT      - counts unique jobId / requisitionId / jobPostingId style
                     identifiers embedded in the page HTML or hydration JSON,
                     which is usually the most reliable count for SPA boards
                     (Workday, etc.) since every posting has exactly one.

Reconciliation prefers the structural DOM/data signals (2 and 3) over the
marketing-copy text signal (1), since #1 is the one that misreports regional
counts as a global total.
"""
import re
from playwright.async_api import async_playwright

TEXT_COUNT_PATTERNS = [
    re.compile(
        r"([\d,]{1,6})\+?\s*(?:open\s+)?(?:job|jobs|opening|openings|position|positions|posting|postings|vacanc(?:y|ies))\b",
        re.I,
    ),
    re.compile(
        r"(?:job|jobs|opening|openings|position|positions|posting|postings)\s*[:\-]?\s*([\d,]{1,6})\+?",
        re.I,
    ),
]

# Broad net of selectors seen across Greenhouse/Lever clones, Workday,
# Oracle HCM, Skima, and typical in-house React/Vue boards. Every selector is
# tried; the largest non-zero match count wins (see _pick_card_count).
CARD_SELECTORS = [
    '[class*="job-card" i]', '[class*="jobcard" i]', '[class*="job-listing" i]',
    '[class*="job-item" i]', '[class*="joblist" i] li', '[class*="job-tile" i]',
    'li[class*="job" i]', 'div[class*="job-row" i]', '[data-automation-id*="job" i]',
    '[class*="career" i][class*="card" i]', '[data-testid*="job" i]',
    'article[class*="job" i]', 'tr[class*="job" i]', '[class*="requisition" i]',
    '[class*="vacancy" i]', 'a[href*="job" i][class*="card" i]',
]

ID_PATTERNS = [
    re.compile(r'"jobId"\s*:\s*"?([\w\-]+)"?', re.I),
    re.compile(r'"requisitionId"\s*:\s*"?([\w\-]+)"?', re.I),
    re.compile(r'"req_id"\s*:\s*"?([\w\-]+)"?', re.I),
    re.compile(r'"jobPostingId"\s*:\s*"?([\w\-]+)"?', re.I),
    re.compile(r'requisition[_\-]?id["\']?\s*[:=]\s*["\']?([\w\-]+)', re.I),
]

# Above this many matched cards, per-card extraction (one JS eval per field
# set) stops being worth the page load it adds; fall back to the count-only
# signals instead and note it in the debug output.
MAX_CARDS_TO_EXTRACT = 800

_EXTRACT_JS = """
(elements) => elements.map(el => {
  const pickText = (sel) => {
    const found = el.querySelector(sel);
    return found ? found.innerText.trim() : null;
  };
  const titleEl = el.querySelector('h1,h2,h3,h4,h5,a,[class*="title" i]');
  const linkEl = el.tagName === 'A' ? el : el.querySelector('a[href]');
  const rawTitle = titleEl ? titleEl.innerText : el.innerText || '';
  return {
    title: rawTitle.trim().split('\\n')[0].slice(0, 200) || null,
    url: linkEl ? linkEl.href : null,
    location: pickText('[class*="location" i]'),
    department: pickText('[class*="department" i], [class*="category" i], [class*="team" i], [class*="function" i]'),
  };
})
"""


async def scrape_custom_source(url: str) -> dict:
    result = {
        "method": "custom_playwright",
        "text_match": None,
        "card_count": None,
        "card_selector_used": None,
        "id_count": None,
        "final_count": 0,
        "jobs": [],
        "notes": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            await page.goto(url, wait_until="networkidle", timeout=45000)
            # SPA job boards (Workday etc.) hydrate after the network goes
            # idle; give the client-side render a moment to finish.
            await page.wait_for_timeout(2500)

            await _try_apply_india_filter(page)

            body_text = await page.inner_text("body")
            html = await page.content()

            result["text_match"] = _pick_text_count(body_text)
            result["card_count"], result["card_selector_used"] = await _pick_card_count(page)
            result["id_count"] = _pick_id_count(html)
            result["final_count"] = _reconcile(result)

            if result["card_selector_used"] and result["card_count"] <= MAX_CARDS_TO_EXTRACT:
                result["jobs"] = await _extract_jobs(page, result["card_selector_used"], url)
            elif result["card_count"] and result["card_count"] > MAX_CARDS_TO_EXTRACT:
                result["notes"].append(
                    f"skipped per-job extraction ({result['card_count']} cards > cap); count-only"
                )

        except Exception as e:
            result["notes"].append(f"scrape error: {e}")
            result["final_count"] = 0
        finally:
            await browser.close()

    return result


async def _try_apply_india_filter(page):
    """Best-effort: if the board exposes a location/country search box, type
    'India' into it so the three signals below are counted on a pre-filtered
    page rather than the global list. Silently no-ops if nothing matches --
    some boards need a site-specific URL param instead (handled by the admin
    supplying an already India-filtered URL, as in the Workday example with
    ?locationCountry= in the query string).
    """
    try:
        loc_input = page.locator(
            'input[placeholder*="location" i], input[aria-label*="location" i], '
            'input[placeholder*="country" i], input[aria-label*="country" i]'
        ).first
        if await loc_input.count() > 0:
            await loc_input.click()
            await loc_input.fill("India")
            await page.wait_for_timeout(1000)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
    except Exception:
        pass


def _pick_text_count(body_text: str) -> int | None:
    candidates = []
    for pattern in TEXT_COUNT_PATTERNS:
        for m in pattern.finditer(body_text):
            try:
                n = int(m.group(1).replace(",", ""))
                if 0 < n < 100000:
                    candidates.append(n)
            except ValueError:
                continue
    if not candidates:
        return None
    # The page's own "showing X results" label tends to be the smallest
    # plausible hit; larger numbers are usually unrelated stats/marketing copy.
    return min(candidates)


async def _extract_jobs(page, selector: str, page_url: str) -> list[dict]:
    """Pulls title/url/location/department out of every matched card in one
    batched JS evaluation (cheap — a single round trip regardless of how
    many cards there are), then de-dupes and shapes each into the same
    {external_id, title, location, department, url, raw} form the API-based
    handlers use, so tasks.py can treat every source type identically.
    """
    try:
        raw_items = await page.eval_on_selector_all(selector, _EXTRACT_JS)
    except Exception:
        return []

    seen = set()
    jobs = []
    for item in raw_items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        job_url = item.get("url") or page_url
        key = (title, job_url)
        if key in seen:
            continue
        seen.add(key)
        jobs.append({
            "external_id": job_url,
            "title": title,
            "location": (item.get("location") or "").strip() or None,
            "department": (item.get("department") or "").strip() or None,
            "url": job_url,
            "raw": item,
        })
    return jobs


async def _pick_card_count(page) -> tuple[int, str | None]:
    best_count, best_selector = 0, None
    for sel in CARD_SELECTORS:
        try:
            count = await page.locator(sel).count()
        except Exception:
            continue
        if count > best_count:
            best_count, best_selector = count, sel
    return best_count, best_selector


def _pick_id_count(html: str) -> int:
    ids = set()
    for pattern in ID_PATTERNS:
        for m in pattern.finditer(html):
            ids.add(m.group(1))
    return len(ids)


def _reconcile(result: dict) -> int:
    """Structural DOM/data signals (card count, id count) are trusted over the
    text-based claim, since the text claim is exactly what misreports a
    global total as the page's headline number. When both structural signals
    exist and roughly agree, take the larger (duplicate cards/ids undercount,
    but a stray unrelated element rarely *overcounts* by more than 2x).
    When they disagree wildly, fall back to whichever is non-zero and
    smaller, since over-broad selectors are the more common failure mode.
    """
    text_c = result["text_match"] or 0
    card_c = result["card_count"] or 0
    id_c = result["id_count"] or 0

    structural = [c for c in (card_c, id_c) if c > 0]
    if len(structural) == 2:
        lo, hi = min(structural), max(structural)
        if hi <= lo * 2:
            return hi
        return lo
    if structural:
        return structural[0]
    return text_c
