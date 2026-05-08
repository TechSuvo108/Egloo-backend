import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.brain_service import check_brain_health

@pytest.fixture
def mock_health_deps():
    db = AsyncMock()
    with patch("app.services.brain_service.get_redis") as m_redis, \
         patch("app.utils.chroma_client.get_chroma_client") as m_chroma, \
         patch("app.ai.llm_router.get_active_provider_async", new_callable=AsyncMock) as m_llm:
        
        # Mock successful connections
        m_redis.return_value.ping = AsyncMock(return_value=True)
        m_redis.return_value.get = AsyncMock(return_value=b"2026-05-08T10:00:00+00:00")
        m_chroma.return_value.heartbeat = MagicMock()
        m_llm.return_value = "gemini"
        
        yield db, m_redis, m_chroma, m_llm

@pytest.mark.asyncio
async def test_check_brain_health_healthy(mock_health_deps):
    db, m_redis, m_chroma, m_llm = mock_health_deps
    
    # Mock current time to be within 3 mins of heartbeat
    from datetime import datetime, timezone
    with patch("datetime.datetime") as mock_date:
        mock_date.now.return_value = datetime.fromisoformat("2026-05-08T10:01:00+00:00")
        mock_date.fromisoformat.side_effect = datetime.fromisoformat
        
        health = await check_brain_health(db)
        
        assert health["status"] == "healthy"
        assert health["postgres"] is True
        assert health["redis"] is True
        assert health["chroma"] is True
        assert health["scheduler"] is True
        assert health["llm"] == "gemini"

@pytest.mark.asyncio
async def test_check_brain_health_degraded(mock_health_deps):
    db, m_redis, m_chroma, m_llm = mock_health_deps
    
    # Mock ChromaDB failure
    m_chroma.return_value.heartbeat.side_effect = Exception("Chroma down")
    
    health = await check_brain_health(db)
    
    assert health["status"] == "degraded"
    assert health["chroma"] is False
    assert health["postgres"] is True

@pytest.mark.asyncio
async def test_check_brain_health_down(mock_health_deps):
    db, m_redis, m_chroma, m_llm = mock_health_deps
    
    # Mock Postgres failure
    db.execute.side_effect = Exception("DB connection lost")
    
    health = await check_brain_health(db)
    
    assert health["status"] == "down"
    assert health["postgres"] is False
