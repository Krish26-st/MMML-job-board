"""Dynamic handler for any jobs.ashbyhq.com careers URL.

Ashby publishes a free public JSON API per job board:
  https://api.ashbyhq.com/posting-api/job-board/{boardName}

Filtering (India/remote + finance relevance) is applied centrally in
tasks.py.
"""
import httpx
from .detector import extract_ashby_board_name


async def fetch_ashby_jobs(url: str) -> dict:
    board = extract_ashby_board_name(url)
    if not board:
        raise ValueError(f"Could not extract an Ashby job board name from {url}")

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(api_url)
        resp.raise_for_status()
        data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        location = j.get("location") or ""
        if j.get("isRemote") and "remote" not in location.lower():
            location = f"{location} (Remote)".strip()
        department = ", ".join(filter(None, [j.get("department"), j.get("team")]))
        jobs.append({
            "external_id": j.get("id"),
            "title": j.get("title"),
            "location": location,
            "department": department,
            "url": j.get("jobUrl") or j.get("applyUrl"),
            "raw": {"id": j.get("id"), "title": j.get("title"), "location": location},
        })

    return {"jobs": jobs, "method": "ashby_api"}
