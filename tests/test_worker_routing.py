import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ingestion_service import ingest_source
from app.models.source import DataSource
from uuid import uuid4

@pytest.mark.asyncio
async def test_ingest_source_skips_pdf_upload():
    """Verify that pdf_upload sources are skipped without error."""
    db = AsyncMock()
    user_id = str(uuid4())
    source = DataSource(
        id=uuid4(),
        user_id=uuid4(),
        source_type="pdf_upload",
        sync_status="idle"
    )
    
    result = await ingest_source(db, source, user_id)
    
    assert result["skipped"] is True
    assert "pdf_upload" in result["source_type"]
    assert source.sync_status == "success"
    # Verify commit called (for status update)
    assert db.commit.called
