import asyncio
from datetime import datetime
from celery import Celery, chain

from .config import settings
from .database import SessionLocal
from .models import Source, Job
from .scrapers.detector import detect_source_type
from .scrapers.greenhouse import fetch_greenhouse_jobs
from .scrapers.lever import fetch_lever_jobs
from .scrapers.workday import fetch_workday_jobs
from .scrapers.ashby import fetch_ashby_jobs
from .scrapers.custom import scrape_custom_source
from .scrapers.filters import passes_all_filters

celery_app = Celery("mmml_job_board", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    # Belt-and-braces alongside `celery -A app.tasks worker --concurrency=1`:
    # only ever pull one task off the queue at a time, so a single Chromium
    # instance is running at any given moment.
    worker_prefetch_multiplier=1,
    task_track_started=True,
    beat_schedule={
        "sync-all-every-24h": {
            "task": "app.tasks.sync_all_sources",
            "schedule": 24 * 60 * 60,  # seconds
        },
    },
)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.sync_source", bind=True, max_retries=2, default_retry_delay=60)
def sync_source(self, source_id: int):
    db = SessionLocal()
    try:
        source = db.get(Source, source_id)
        if not source:
            return {"error": "source not found"}

        source.status = "syncing"
        db.commit()

        try:
            source_type = source.source_type or detect_source_type(source.url)

            if source_type == "greenhouse":
                data = _run_async(fetch_greenhouse_jobs(source.url))
            elif source_type == "lever":
                data = _run_async(fetch_lever_jobs(source.url))
            elif source_type == "workday":
                data = _run_async(fetch_workday_jobs(source.url))
            elif source_type == "ashby":
                data = _run_async(fetch_ashby_jobs(source.url))
            else:
                source_type = "custom"
                data = _run_async(scrape_custom_source(source.url))
                data.setdefault("jobs", [])

            raw_jobs = data.get("jobs", [])

            # --- Strict filter 1 (India or remote) + filter 2 (finance-related) ---
            filtered_jobs = [
                j for j in raw_jobs
                if passes_all_filters(j.get("title"), j.get("location"), j.get("department"))
            ]

            # The custom scraper is the one case where individual postings
            # can fail to extract (e.g. > MAX_CARDS_TO_EXTRACT, or an
            # unusual layout) even though its 3-signal heuristic still
            # produced a page-wide count. Filters need per-job data to run,
            # so when extraction came back empty we fall back to the
            # unfiltered heuristic count and say so explicitly in the debug
            # info, rather than silently reporting 0 or an unfiltered total
            # as if it had been filtered.
            used_unfiltered_fallback = source_type == "custom" and not raw_jobs and data.get("final_count", 0) > 0

            db.query(Job).filter(Job.source_id == source.id).delete()
            for j in filtered_jobs:
                db.add(Job(
                    source_id=source.id,
                    external_id=j.get("external_id"),
                    title=j.get("title"),
                    location=j.get("location"),
                    url=j.get("url"),
                    raw=j.get("raw"),
                ))

            source.job_count = data.get("final_count", 0) if used_unfiltered_fallback else len(filtered_jobs)
            source.source_type = source_type
            source.status = "active"
            source.last_error = None
            source.last_sync = datetime.utcnow()
            source.detection_debug = {
                **{k: v for k, v in data.items() if k != "jobs"},
                "fetched_before_filters": len(raw_jobs),
                "passed_filters": len(filtered_jobs),
                "unfiltered_fallback_used": used_unfiltered_fallback,
            }

        except Exception as e:
            source.status = "error"
            source.last_error = str(e)[:2000]

        db.commit()
        return {"source_id": source_id, "job_count": source.job_count, "status": source.status}
    finally:
        db.close()


@celery_app.task(name="app.tasks.sync_all_sources")
def sync_all_sources():
    """Kicks off every active source's sync as a Celery *chain*, so each
    sync_source call only starts once the previous one has fully finished --
    this is what guarantees one-Playwright-browser-at-a-time regardless of
    how many sources exist or how the worker is scaled.
    """
    db = SessionLocal()
    try:
        ids = [s.id for s in db.query(Source).all()]
    finally:
        db.close()

    if not ids:
        return {"queued": 0}

    workflow = chain(sync_source.si(i) for i in ids)
    workflow.apply_async()
    return {"queued": len(ids)}
