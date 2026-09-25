import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..scrapers.detector import detect_source_type
from ..tasks import sync_source, sync_all_sources

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalize_url(raw: str) -> str:
    """Every detector here relies on urlparse finding a real netloc, which
    silently fails (falls through to 'custom') if the URL has no scheme --
    e.g. 'yelp.myworkdayjobs.com/Yelp' pasted without 'https://'. Rather
    than rely on the admin always remembering to type the scheme, add it
    here if it's missing.
    """
    url = raw.strip()
    if not re.match(r"^https?://", url, re.I):
        url = f"https://{url}"
    return url


@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.query(models.Source).order_by(models.Source.created_at.desc()).all()


@router.post("/sources", response_model=schemas.SourceOut)
def add_source(payload: schemas.SourceCreate, db: Session = Depends(get_db)):
    url = _normalize_url(payload.url)
    existing = db.query(models.Source).filter(models.Source.url == url).first()
    if existing:
        raise HTTPException(400, "This URL is already added")

    source = models.Source(
        company_name=payload.company_name.strip(),
        url=url,
        source_type=detect_source_type(url),
        status="active",
        job_count=0,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    # The row above is already saved at this point -- if queuing the first
    # sync fails (e.g. the broker is briefly unreachable), that shouldn't
    # surface as a generic 500 that makes it look like nothing happened.
    # Save the source anyway and let the admin retry with the sync button.
    try:
        sync_source.delay(source.id)
    except Exception as e:
        source.last_error = f"Source added, but couldn't queue the first sync: {e}"
        db.commit()
        db.refresh(source)

    return source


@router.post("/sources/{source_id}/sync")
def sync_one(source_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Source, source_id):
        raise HTTPException(404, "Source not found")
    try:
        sync_source.delay(source_id)
    except Exception as e:
        raise HTTPException(503, f"Couldn't reach the job queue: {e}")
    return {"queued": True}


@router.post("/sources/sync-all")
def sync_all():
    try:
        sync_all_sources.delay()
    except Exception as e:
        raise HTTPException(503, f"Couldn't reach the job queue: {e}")
    return {"queued": True}


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    db.delete(source)
    db.commit()
    return {"deleted": True}
