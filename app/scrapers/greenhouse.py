"""Dynamic handler for any greenhouse.io careers URL.

Greenhouse exposes a free, undocumented-but-stable public JSON API for every
board: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

No Playwright needed here — this is fast, exact, and never miscounts like a
DOM scrape can. Location/relevance filtering is applied centrally in
tasks.py (see app/scrapers/filters.py) so every source type is filtered the
same way.
"""
import httpx
from .detector import extract_greenhouse_token


async def fetch_greenhouse_jobs(url: str) -> dict:
    token = extract_greenhouse_token(url)
    if not token:
        raise ValueError(f"Could not extract a Greenhouse board token from {url}")

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(api_url)
        resp.raise_for_status()
        data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        departments = ", ".join(d.get("name", "") for d in j.get("departments", []) if d.get("name"))
        jobs.append({
            "external_id": str(j.get("id")),
            "title": j.get("title"),
            "location": loc,
            "department": departments,
            "url": j.get("absolute_url"),
            "raw": {"id": j.get("id"), "title": j.get("title"), "location": loc, "departments": departments},
        })

    return {"jobs": jobs, "method": "greenhouse_api"}
