"""Dynamic handler for any lever.co careers URL.

Lever exposes a free public JSON API for every posting board:
https://api.lever.co/v0/postings/{site}?mode=json

Filtering is applied centrally in tasks.py (see app/scrapers/filters.py).
"""
import httpx
from .detector import extract_lever_site


async def fetch_lever_jobs(url: str) -> dict:
    site = extract_lever_site(url)
    if not site:
        raise ValueError(f"Could not extract a Lever site slug from {url}")

    api_url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(api_url)
        resp.raise_for_status()
        data = resp.json()

    jobs = []
    for j in data:
        categories = j.get("categories") or {}
        loc = categories.get("location") or ""
        department = ", ".join(filter(None, [categories.get("team"), categories.get("department")]))
        jobs.append({
            "external_id": j.get("id"),
            "title": j.get("text"),
            "location": loc,
            "department": department,
            "url": j.get("hostedUrl"),
            "raw": {"id": j.get("id"), "title": j.get("text"), "location": loc, "department": department},
        })

    return {"jobs": jobs, "method": "lever_api"}
