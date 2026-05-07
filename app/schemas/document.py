from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class DocumentResponse(BaseModel):
    id: UUID
    user_id: UUID
    source_type: str
    filename: str
    page_count: int
    sync_status: str
    file_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PDFUploadAcceptedResponse(BaseModel):
    message: str
    document_id: UUID
    job_id: str


class PDFUploadSuccessResponse(BaseModel):
    message: str
    document_id: UUID
    chunks_created: int
