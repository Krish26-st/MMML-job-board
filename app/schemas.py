from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, field_serializer


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

    @field_serializer("last_sync", "created_at")
    def _serialize_as_utc(self, value: Optional[datetime], _info):
        # SQLite in particular hands back naive datetimes even though every
        # value written into these columns is UTC -- tag it explicitly so
        # the browser's Date parser (and our IST formatting) treats it as
        # UTC instead of silently assuming it's already local time.
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
