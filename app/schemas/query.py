from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any

class AskRequest(BaseModel):
    question: str
    use_cache: bool = True

class SourceCitation(BaseModel):
    document_id: str
    source_type: str
    sender: Optional[str] = ""
    subject: Optional[str] = ""
    timestamp: Optional[str] = ""
    content_preview: str
    similarity: Optional[float] = 0

class AskResponse(BaseModel):
    answer: str
    sources: List[SourceCitation]
    model_used: str
    chunks_retrieved: int
    cached: bool
    question: str

class QueryHistoryItem(BaseModel):
    id: UUID
    question: str
    answer: Optional[str]
    sources_used: Optional[List[Any]]
    model_used: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

class QueryHistoryResponse(BaseModel):
    history: List[QueryHistoryItem]
    total: int
