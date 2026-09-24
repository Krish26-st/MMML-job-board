from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..scrapers.detector import detect_source_type
from ..tasks import sync_source, sync_all_sources

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.query(models.Source).order_by(models.Source.created_at.desc()).all()


@router.post("/sources", response_model=schemas.SourceOut)
def add_source(payload: schemas.SourceCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Source).filter(models.Source.url == payload.url).first()
    if existing:
        raise HTTPException(400, "This URL is already added")

    source = models.Source(
        company_name=payload.company_name.strip(),
        url=payload.url.strip(),
        source_type=detect_source_type(payload.url),
        status="active",
        job_count=0,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    sync_source.delay(source.id)  # kick off an immediate first sync
    return source


@router.post("/sources/{source_id}/sync")
def sync_one(source_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Source, source_id):
        raise HTTPException(404, "Source not found")
    sync_source.delay(source_id)
    return {"queued": True}


@router.post("/sources/sync-all")
def sync_all():
    sync_all_sources.delay()
    return {"queued": True}


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    db.delete(source)
    db.commit()
    return {"deleted": True}
