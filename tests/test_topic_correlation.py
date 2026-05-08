import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.topic_correlation_service import correlate_topics

@pytest.fixture
def mock_dependencies():
    with patch("app.services.topic_correlation_service.retrieve_chunks", new_callable=AsyncMock) as m_retrieve, \
         patch("app.services.topic_correlation_service.cluster_chunks", new_callable=AsyncMock) as m_cluster:
        m_retrieve.return_value = []
        m_cluster.return_value = []
        yield m_retrieve, m_cluster

@pytest.mark.asyncio
async def test_correlate_topics_filtering_and_dedup(mock_dependencies):
    m_retrieve, m_cluster = mock_dependencies
    
    user_id = "test-user"
    recent_chunks = [
        # Normal chunk
        {"content": "Meeting about the new parser logic", "metadata": {"source_type": "slack"}},
        # Duplicate chunk
        {"content": "Meeting about the new parser logic", "metadata": {"source_type": "slack"}},
        # Noise (resume-like)
        {"content": "Objective: Software Engineer. Skills: Python, JS. Experience: 5 years.", "metadata": {"source_type": "pdf"}},
        # Urgent chunk
        {"content": "URGENT: Blocked by auth bug in the upload module", "metadata": {"source_type": "slack"}}
    ]
    
    # Mock cluster result
    m_cluster.return_value = [
        {"name": "Parser & Auth", "summary": "Fixing things", "chunk_indices": [0, 1], "source_types": ["slack"]}
    ]
    
    await correlate_topics(user_id, recent_chunks)
    
    # Verify filtering: 
    # - 1 duplicate removed by hash
    # - 1 noise removed by _is_noise
    # Original (4) -> filtered (3) -> deduped (2)
    # Wait, dedup happens after filtering. 
    # Filtered: [Normal, Duplicate, Urgent] (3)
    # Deduped: [Normal, Urgent] (2)
    
    # The logs should show:
    # [BRAIN] filtered 1 noise chunks
    # [BRAIN] deduped to 2 chunks
    
    # Verify cluster_chunks called with 2 chunks
    args, kwargs = m_cluster.call_args
    assert len(args[0]) == 2
    
    # Verify importance weighting
    urgent_chunk = next(c for c in args[0] if "URGENT" in c["content"])
    assert urgent_chunk["importance"] > 0

@pytest.mark.asyncio
async def test_correlate_topics_empty(mock_dependencies):
    m_retrieve, m_cluster = mock_dependencies
    assert await correlate_topics("user", []) == []
