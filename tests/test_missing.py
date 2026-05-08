import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.missing_service import get_missing_items
from app.models.document_chunk import DocumentChunk

@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_scalars.all.return_value = []
    db.execute.return_value = mock_result
    return db

@pytest.fixture
def mock_redis():
    with patch("app.services.missing_service.get_redis") as m_get_redis:
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        m_get_redis.return_value = mock_client
        yield mock_client

@pytest.mark.asyncio
async def test_get_missing_items_with_alerts(mock_db, mock_redis):
    """Scenario: Analyze gaps using both chunks and proactive alerts."""
    user_id = uuid4()
    
    # 1. Mock DB Chunks
    chunks = [
        DocumentChunk(
            content="Can you review the proposal by Monday?",
            chunk_metadata={"source_type": "gmail", "sender": "manager@work.com"},
            created_at=datetime.now(timezone.utc)
        )
    ]
    mock_db.execute.return_value.scalars.return_value.all.return_value = chunks
    
    # 2. Mock Redis Alerts
    mock_alerts = [
        {"type": "urgent", "message": "SLACK urgent: payment pending for AWS"}
    ]
    
    mock_json = {
        "missing": [
            "Review proposal (from manager@work.com)",
            "AWS payment pending (from Slack alert)"
        ]
    }
    
    with patch("app.services.missing_service.get_alerts", new_callable=AsyncMock) as mock_get_alerts:
        mock_get_alerts.return_value = mock_alerts
        
        with patch("app.services.missing_service.call_llm_simple", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (json.dumps(mock_json), "gemini")
            
            result = await get_missing_items(mock_db, user_id)
            
            assert len(result["missing"]) == 2
            assert "AWS payment" in result["missing"][1]
            assert result["model_used"] == "gemini"
            
            # Verify logs (optional but good)
            # We can't easily verify print() unless we capture stdout, 
            # but we know it reached here if assertions pass.

@pytest.mark.asyncio
async def test_get_missing_items_empty(mock_db, mock_redis):
    """Scenario: No data and no alerts."""
    user_id = uuid4()
    
    with patch("app.services.missing_service.get_alerts", new_callable=AsyncMock) as mock_get_alerts:
        mock_get_alerts.return_value = []
        
        with patch("app.services.missing_service.call_llm_simple", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ("{\"missing\": []}", "gemini")
            
            result = await get_missing_items(mock_db, user_id)
            assert result["missing"] == []
