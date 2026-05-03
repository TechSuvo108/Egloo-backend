from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class SourceResponse(BaseModel):
    id: UUID
    source_type: str
    sync_status: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    sources: list[SourceResponse]
    total: int


class SyncStatusResponse(BaseModel):
    source_id: UUID
    source_type: str
    sync_status: str
    last_synced_at: Optional[datetime] = None
    message: str


class MessageResponse(BaseModel):
    message: str
