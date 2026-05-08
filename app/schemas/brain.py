from pydantic import BaseModel, Field
from typing import List, Optional

class BrainTodayResponse(BaseModel):
    """Proactive daily summary of user activity."""
    priorities: List[str] = Field(default_factory=list)
    blocked: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    suggested_first_step: str
    model_used: Optional[str] = None

class BrainMissingResponse(BaseModel):
    """Analysis of gaps, missed items, and pending work."""
    missing: List[str] = Field(default_factory=list)
    model_used: Optional[str] = None

class BrainConnection(BaseModel):
    """A semantically clustered connection across sources."""
    topic: str
    related_sources: List[str]
    urgency_score: int = Field(ge=1, le=10)
    suggested_action: str
    summary: str

class BrainConnectionsResponse(BaseModel):
    """List of all discovered connections."""
    connections: List[BrainConnection] = Field(default_factory=list)
    model_used: Optional[str] = None
