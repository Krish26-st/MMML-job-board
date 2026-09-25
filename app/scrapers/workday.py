"""Dynamic handler for any *.myworkdayjobs.com careers URL (Workday CXS).

Workday's frontend calls an internal-but-public JSON API to render its job
list, which we can call directly instead of driving a browser:

  POST https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  body: {"appliedFacets": {}, "limit": 20, "offset": <n>, "searchText": ""}

This is paginated, so results are pulled page by page until Workday reports
no more are left (capped at MAX_JOBS as a sanity limit). No browser, no
selector guessing — this replaces what used to be a custom-scraper job for
Workday boards (e.g. the LSEG India source in the admin panel).

Filtering (India/remote + finance relevance) is applied centrally in
tasks.py.
"""
import httpx
from .detector import extract_workday_parts

PAGE_SIZE = 20
MAX_JOBS = 2000


async def fetch_workday_jobs(url: str) -> dict:
    parts = extract_workday_parts(url)
    if not parts:
        raise ValueError(f"Could not parse a Workday tenant/site from {url}")

    api_url = f"https://{parts['host']}/wday/cxs/{parts['tenant']}/{parts['site']}/jobs"
    base_url = f"https://{parts['host']}"

    jobs = []
    offset = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while offset < MAX_JOBS:
            resp = await client.post(
                api_url,
                json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("jobPostings", [])
            if not postings:
                break

            for p in postings:
                external_path = p.get("externalPath", "")
                jobs.append({
                    "external_id": external_path or p.get("bulletFields", [None])[0],
                    "title": p.get("title"),
                    "location": p.get("locationsText"),
                    "department": None,
                    "url": f"{base_url}{external_path}" if external_path else url,
                    "raw": {"title": p.get("title"), "location": p.get("locationsText"), "path": external_path},
                })

            offset += PAGE_SIZE
            if offset >= data.get("total", 0):
                break

    return {"jobs": jobs, "method": "workday_api"}
