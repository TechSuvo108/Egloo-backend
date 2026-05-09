import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.models.source import DataSource
from app.utils.chroma_client import get_or_create_collection
from app.utils.chunker import chunk_text
from app.utils.embedder import embed_texts
from app.services.source_service import (
    get_decrypted_access_token,
    get_decrypted_refresh_token,
)
from app.services.alert_service import scan_and_store_alerts


# ---------------------------------------------------------------------------
# Internal helper — update sync_status + optional last_synced_at
# ---------------------------------------------------------------------------

async def _update_sync_status(
    db: AsyncSession,
    source: DataSource,
    status: str,
    last_synced_at: Optional[datetime] = None,
) -> None:
    source.sync_status = status
    if last_synced_at is not None:
        source.last_synced_at = last_synced_at
    await db.commit()


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

async def ingest_source(
    db: AsyncSession,
    source: DataSource,
    user_id: str,
) -> Dict[str, Any]:
    """
    Full ingestion pipeline for a single DataSource.

    Steps:
    1. Decrypt tokens from DB
    2. Fetch raw documents from the source API
    3. Chunk each document
    4. Embed all chunks in batches
    5. Delete stale vectors from ChromaDB
    6. Store new vectors in ChromaDB
    7. Delete stale chunk records from PostgreSQL
    8. Save new chunk records to PostgreSQL
    9. Update source sync status

    Returns a summary dict with counts.
    """
    source_id = str(source.id)
    source_type = source.source_type

    await _update_sync_status(db, source, "syncing")
    print(f"🐧 Pingo starting ingestion for {source_type}...")

    # ── Special Case: PDF Uploads ─────────────────────────────────────────────
    # Requirement: gracefully skip if already synchronously processed
    if source_type == "pdf_upload":
        print(f"[WORKER] {source_type} already processed")
        await _update_sync_status(
            db, source, "success",
            last_synced_at=datetime.now(timezone.utc),
        )
        return {
            "source_type": source_type,
            "message": "PDF sources are processed during upload and skip background sync.",
            "skipped": True
        }

    try:
        # ── Step 1: Decrypt tokens ──────────────────────────────────────────
        access_token = get_decrypted_access_token(source)
        refresh_token = get_decrypted_refresh_token(source)

        if not access_token:
            raise ValueError(f"No access token found for source {source_id}")

        # ── Step 2: Fetch raw documents ─────────────────────────────────────
        raw_documents = await _fetch_documents(
            source_type=source_type,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        if not raw_documents:
            await _update_sync_status(
                db, source, "success",
                last_synced_at=datetime.now(timezone.utc),
            )
            return {
                "source_type": source_type,
                "documents_fetched": 0,
                "chunks_created": 0,
                "message": "No new documents found",
            }

        # ── Step 3: Chunk all documents ─────────────────────────────────────
        all_chunks: List[Dict[str, Any]] = []
        for doc in raw_documents:
            metadata = {
                "source_type": doc["source_type"],
                "document_id": doc["document_id"],
                "timestamp": doc.get("timestamp", ""),
                "sender": doc.get("sender", doc.get("channel", "")),
                "subject": doc.get("subject", doc.get("title", "")),
                "source_id": source_id,
                "user_id": user_id,
            }
            chunks = chunk_text(doc["content"], metadata)
            all_chunks.extend(chunks)

        print(f"📄 Created {len(all_chunks)} chunks from {len(raw_documents)} documents")

        if not all_chunks:
            await _update_sync_status(
                db, source, "success",
                last_synced_at=datetime.now(timezone.utc),
            )
            return {
                "source_type": source_type,
                "documents_fetched": len(raw_documents),
                "chunks_created": 0,
                "message": "Documents were empty after parsing",
            }

        # ── Step 4: Embed chunks in batches ─────────────────────────────────
        batch_size = 32
        all_embeddings: List[List[float]] = []
        texts = [c["content"] for c in all_chunks]

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = embed_texts(batch)
            all_embeddings.extend(embeddings)
            batch_num = i // batch_size + 1
            total_batches = (len(texts) + batch_size - 1) // batch_size
            print(f"🔢 Embedded batch {batch_num} / {total_batches}")

        # ── Step 5: Delete stale vectors for this source from ChromaDB ───────
        collection = get_or_create_collection(user_id)
        try:
            collection.delete(where={"source_id": source_id})
        except Exception:
            pass  # Collection might be empty — that's fine

        # ── Step 6: Store new vectors in ChromaDB ───────────────────────────
        chroma_ids = [str(uuid.uuid4()) for _ in all_chunks]

        collection.add(
            ids=chroma_ids,
            documents=texts,
            embeddings=all_embeddings,
            metadatas=[c["metadata"] for c in all_chunks],
        )

        print(f"✅ Stored {len(chroma_ids)} vectors in ChromaDB")

        # ── Step 7: Delete stale PostgreSQL chunk records for this source ─────
        await db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.source_id == source.id
            )
        )

        # ── Step 8: Save new chunk records to PostgreSQL ─────────────────────
        pg_chunks = [
            DocumentChunk(
                user_id=uuid.UUID(user_id),
                source_id=source.id,
                content=chunk["content"],
                chunk_metadata=chunk["metadata"],
                chroma_id=chroma_ids[i],
            )
            for i, chunk in enumerate(all_chunks)
        ]
        db.add_all(pg_chunks)
        await db.commit()

        print(f"✅ Saved {len(pg_chunks)} chunk records to PostgreSQL")

        # ── Step 9: Update source status ─────────────────────────────────────
        await _update_sync_status(
            db, source, "success",
            last_synced_at=datetime.now(timezone.utc),
        )

        # ── Step 10: Scan for proactive alerts ───────────────────────────────
        try:
            await scan_and_store_alerts(user_id, all_chunks)
        except Exception as e:
            print(f"⚠️  Alert scanning failed: {e}")

        return {
            "source_type": source_type,
            "documents_fetched": len(raw_documents),
            "chunks_created": len(all_chunks),
            "vectors_stored": len(chroma_ids),
            "message": f"Pingo successfully ingested {source_type}! 🐧",
        }

    except Exception as e:
        # ── Handle Auth Failures (Stop Retry Storm) ───────────────────────────
        from cryptography.fernet import InvalidToken
        error_msg = str(e).lower()
        
        # Check for decryption failure or API auth failure
        is_auth_failure = (
            isinstance(e, InvalidToken) or
            any(kw in error_msg for kw in ["401", "unauthorized", "invalid_grant", "expired_token", "invalid token"])
        )

        if is_auth_failure:
            print(f"⚠️ [AUTH] Permanent authentication failure for {source_type}: {e}")
            await _update_sync_status(db, source, "auth_expired")
            # We return instead of raising to STOP Celery from retrying
            return {
                "source_type": source_type,
                "error": str(e),
                "status": "auth_expired",
                "message": f"Authentication for {source_type} failed. Please reconnect.",
            }

        print(f"❌ Ingestion failed for {source_type}: {e}")
        await _update_sync_status(db, source, "error")
        raise


# ---------------------------------------------------------------------------
# Internal router — dispatches to the correct fetcher
# ---------------------------------------------------------------------------

async def _fetch_documents(
    source_type: str,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Route to the correct fetcher based on source_type."""
    if source_type == "gmail":
        from app.services.fetchers.gmail_fetcher import fetch_gmail_messages
        # fetch_gmail_messages is synchronous (uses google-api-python-client)
        return fetch_gmail_messages(
            access_token=access_token,
            refresh_token=refresh_token,
            days_back=30,
            max_results=100,
        )

    elif source_type == "slack":
        from app.services.fetchers.slack_fetcher import fetch_slack_messages
        # fetch_slack_messages is async (uses slack_sdk AsyncWebClient)
        return await fetch_slack_messages(
            access_token=access_token,
            days_back=30,
            max_messages_per_channel=200,
        )

    elif source_type == "google_drive":
        from app.services.fetchers.drive_fetcher import fetch_drive_files
        # fetch_drive_files is synchronous (uses google-api-python-client)
        return fetch_drive_files(
            access_token=access_token,
            refresh_token=refresh_token,
            days_back=30,
            max_files=100,
        )

    else:
        raise ValueError(f"Unknown source_type: {source_type}")
