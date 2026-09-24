from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/board")
def board(db: Session = Depends(get_db)):
    sources = (
        db.query(models.Source)
        .filter(models.Source.status != "error")
        .order_by(models.Source.company_name.asc())
        .all()
    )
    return [
        {
            "id": s.id,
            "company": s.company_name,
            "job_count": s.job_count,
            "last_sync": s.last_sync,
        }
        for s in sources
    ]


@router.get("/companies/{source_id}/jobs")
def company_jobs(source_id: int, db: Session = Depends(get_db)):
    jobs = db.query(models.Job).filter(models.Job.source_id == source_id).all()
    return [{"title": j.title, "location": j.location, "url": j.url} for j in jobs]


@router.get("/jobs")
def all_jobs(db: Session = Depends(get_db)):
    """The total complete job list across every active company, all already
    passed through the India-or-remote + finance-relevance filters at sync
    time — nothing further to filter here.
    """
    rows = (
        db.query(models.Job, models.Source.company_name)
        .join(models.Source, models.Job.source_id == models.Source.id)
        .filter(models.Source.status != "error")
        .order_by(models.Source.company_name.asc())
        .all()
    )
    return [
        {
            "company": company_name,
            "source_id": job.source_id,
            "title": job.title,
            "location": job.location,
            "url": job.url,
        }
        for job, company_name in rows
    ]
