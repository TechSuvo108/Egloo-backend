import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ingestion_service import ingest_source
from app.models.source import DataSource
from cryptography.fernet import InvalidToken
from uuid import uuid4

@pytest.mark.asyncio
async def test_ingest_source_handles_invalid_token():
    """Verify that decryption failure marks source as auth_expired and stops retries."""
    db = AsyncMock()
    user_id = str(uuid4())
    source = DataSource(
        id=uuid4(),
        user_id=uuid4(),
        source_type="gmail",
        access_token="invalid-encrypted-blob",
        sync_status="idle"
    )
    
    # Mock decryption failure
    with patch("app.services.ingestion_service.get_decrypted_access_token") as m_decrypt:
        m_decrypt.side_effect = InvalidToken()
        
        result = await ingest_source(db, source, user_id)
        
        assert result["status"] == "auth_expired"
        assert source.sync_status == "auth_expired"
        assert "Authentication" in result["message"]
        # Verify db.commit called (for status update)
        assert db.commit.called

@pytest.mark.asyncio
async def test_ingest_source_handles_api_auth_failure():
    """Verify that 401 API errors mark source as auth_expired."""
    db = AsyncMock()
    user_id = str(uuid4())
    source = DataSource(
        id=uuid4(),
        user_id=uuid4(),
        source_type="slack",
        access_token="encrypted-token",
        sync_status="idle"
    )
    
    # Mock decryption success but API 401
    with patch("app.services.ingestion_service.get_decrypted_access_token", return_value="valid-token"), \
         patch("app.services.ingestion_service._fetch_documents") as m_fetch:
        
        m_fetch.side_effect = Exception("Error code: 401 - Unauthorized")
        
        result = await ingest_source(db, source, user_id)
        
        assert result["status"] == "auth_expired"
        assert source.sync_status == "auth_expired"
        assert db.commit.called
