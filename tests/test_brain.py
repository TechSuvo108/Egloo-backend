import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.services.brain_service import get_brain_today, _extract_json
from app.services.missing_service import get_missing_items
from app.services.alert_service import scan_and_store_alerts
from app.models.document_chunk import DocumentChunk

# ─── Mocks for Database and Redis ─────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Mock the chain db.execute().scalars().all()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_scalars.all.return_value = []
    db.execute.return_value = mock_result
    return db

@pytest.fixture
def mock_redis():
    with patch("app.services.brain_service.get_redis") as m_get_redis:
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        m_get_redis.return_value = mock_client
        yield mock_client

# ─── Tests for get_brain_today ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_brain_today_no_data(mock_db, mock_redis):
    """Scenario: User has no recent data in the last 7 days."""
    # mock_db is already set to return [] by default
    user_id = uuid4()
    result = await get_brain_today(mock_db, user_id)
    
    assert result["priorities"] == []
    assert result["action_items"] == []
    assert "No recent data found" in result["suggested_first_step"]

@pytest.mark.asyncio
async def test_get_brain_today_mixed_data(mock_db, mock_redis):
    """Scenario: User has data from Slack, Gmail, and PDF."""
    user_id = uuid4()
    
    chunks = [
        DocumentChunk(
            content="The PDF parser is blocked by a memory leak.",
            chunk_metadata={"source_type": "pdf_upload", "filename": "specs.pdf"},
            created_at=datetime.now(timezone.utc)
        ),
        DocumentChunk(
            content="Slack message: We need to finalize the budget tomorrow.",
            chunk_metadata={"source_type": "slack", "sender": "Alice"},
            created_at=datetime.now(timezone.utc)
        ),
        DocumentChunk(
            content="Gmail: Meeting for Project Alpha on Friday.",
            chunk_metadata={"source_type": "gmail", "subject": "Sync"},
            created_at=datetime.now(timezone.utc)
        )
    ]
    mock_db.execute.return_value.scalars.return_value.all.return_value = chunks
    
    mock_json = {
        "priorities": ["Fix PDF parser", "Finalize budget", "Project Alpha Sync"],
        "blocked": ["Memory leak in parser"],
        "action_items": ["Review budget", "Prepare for meeting"],
        "suggested_first_step": "Look into the memory leak mentioned in specs.pdf."
    }
    
    with patch("app.services.brain_service.call_llm_simple", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (json.dumps(mock_json), "gemini")
        
        # Avoid actual ChromaDB correlation during unit test
        with patch("app.services.brain_service.correlate_topics", new_callable=AsyncMock) as mock_corr:
            mock_corr.return_value = []
            
            result = await get_brain_today(mock_db, user_id)
            
            assert "Fix PDF parser" in result["priorities"]
            assert len(result["priorities"]) == 3
            assert result["model_used"] == "gemini"

# ─── Tests for Urgency Detection (Alert Service) ──────────────────────────────

@pytest.mark.asyncio
async def test_scan_and_store_alerts_urgency():
    """Scenario: New chunks contain urgency keywords."""
    user_id = "user_123"
    chunks = [
        {"content": "Dinner plans for later", "metadata": {"source_type": "slack"}},
        {"content": "Urgent: deadline for the approval is tomorrow ASAP", "metadata": {"source_type": "gmail", "subject": "Q3 Report"}}
    ]
    
    with patch("app.services.alert_service.get_redis") as m_get_redis:
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        m_get_redis.return_value = mock_client
        
        await scan_and_store_alerts(user_id, chunks)
        
        assert mock_client.set.called
        stored_data = json.loads(mock_client.set.call_args[0][1])
        
        assert len(stored_data) == 1
        alert = stored_data[0]
        assert "urgent" in alert["keywords"]
        assert "deadline" in alert["keywords"]
        assert "tomorrow" in alert["keywords"]
        assert "Q3 Report" in alert["message"]

# ─── Tests for LLM Response Fallback ──────────────────────────────────────────

def test_extract_json_malformed():
    """Scenario: LLM returns text with JSON or completely malformed text."""
    # Case 1: Markdown wrapped
    text_1 = "```json\n{\"priorities\": [\"item1\"]}\n```"
    assert _extract_json(text_1)["priorities"] == ["item1"]
    
    # Case 2: Preamble + JSON
    text_2 = "Sure, here is the result: {\"action_items\": [\"fix bug\"]} - let me know if you need more."
    assert _extract_json(text_2)["action_items"] == ["fix bug"]
    
    # Case 3: Completely malformed
    text_3 = "The model failed to generate JSON."
    result = _extract_json(text_3)
    assert "error" in result
    assert result["raw"] == text_3

# ─── Tests for Missing Items ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_missing_items_logic(mock_db, mock_redis):
    """Scenario: Detect missing tasks from mixed data."""
    user_id = uuid4()
    chunks = [
        DocumentChunk(
            content="Still waiting on your approval for the Mars mission.",
            chunk_metadata={"source_type": "slack", "sender": "Elon"},
            created_at=datetime.now(timezone.utc)
        )
    ]
    mock_db.execute.return_value.scalars.return_value.all.return_value = chunks
    
    mock_json = {
        "missing": ["Approval for Mars mission (from Elon on Slack)"]
    }
    
    with patch("app.services.missing_service.call_llm_simple", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (json.dumps(mock_json), "gemini")
        
        result = await get_missing_items(mock_db, user_id)
        assert len(result["missing"]) == 1
        assert "Mars mission" in result["missing"][0]
