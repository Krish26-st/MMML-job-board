from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class SourceCreate(BaseModel):
    company_name: str
    url: str


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    url: str
    source_type: str
    status: str
    job_count: int
    last_sync: Optional[datetime] = None
    last_error: Optional[str] = None
    detection_debug: Optional[dict[str, Any]] = None
    created_at: datetime
