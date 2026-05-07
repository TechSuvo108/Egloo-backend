import fitz  # PyMuPDF
import uuid
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.uploaded_document import UploadedDocument
from app.models.source import DataSource
from app.models.document_chunk import DocumentChunk
from app.utils.chunker import chunk_text
from app.utils.embedder import embed_texts
from app.utils.chroma_client import get_or_create_collection
from app.services.source_service import upsert_source, get_source_by_type


async def extract_text_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from a PDF file per page using PyMuPDF.
    Returns a list of dicts: [{"page": 1, "content": "..."}]
    """
    pages = []
    doc = fitz.open(file_path)
    
    if doc.is_encrypted:
        raise ValueError("PDF is encrypted and cannot be processed.")

    for i, page in enumerate(doc):
        text = page.get_text().strip()
        pages.append({
            "page_number": i + 1,
            "content": text
        })
    
    doc.close()
    
    # Check if we got any text at all
    total_text = "".join([p["content"] for p in pages]).strip()
    if not total_text:
        raise ValueError("PDF contains no readable text. It may be scanned without OCR.")
        
    return pages


async def process_pdf_ingestion(
    db: AsyncSession,
    user_id: str,
    doc_id: str,
    file_path: str
) -> int:
    """
    Full ingestion pipeline for a PDF:
    1. Extract text
    2. Chunk
    3. Embed
    4. Store in ChromaDB & Postgres
    Returns the number of chunks created.
    """
    user_uuid = uuid.UUID(user_id)
    doc_uuid = uuid.UUID(doc_id)
    
    # Fetch the document record
    result = await db.execute(select(UploadedDocument).where(UploadedDocument.id == doc_uuid))
    doc_record = result.scalar_one_or_none()
    if not doc_record:
        print(f"[ERROR] Document {doc_id} not found in database.")
        return 0

    try:
        doc_record.sync_status = "processing"
        await db.commit()

        # 1. Extract text
        pages = await extract_text_from_pdf(file_path)
        doc_record.page_count = len(pages)

        # 2. Ensure we have a "pdf_upload" DataSource for this user
        # We use dummy tokens as PDF upload doesn't need OAuth
        source = await get_source_by_type(db, user_uuid, "pdf_upload")
        if not source:
            source = await upsert_source(
                db=db,
                user_id=user_uuid,
                source_type="pdf_upload",
                access_token="N/A",
                refresh_token=None,
                token_expiry=None,
                source_metadata={"description": "Manual PDF uploads"}
            )
        
        # 3. Chunk text per page
        all_chunks = []
        for page in pages:
            metadata = {
                "source_type": "pdf_upload",
                "source_id": str(source.id),
                "document_id": str(doc_id),
                "user_id": user_id,
                "filename": doc_record.filename,
                "page_number": page["page_number"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            # Requirement: chunk size ~800, overlap ~120
            chunks = chunk_text(page["content"], metadata, chunk_size=800, chunk_overlap=120)
            all_chunks.extend(chunks)

        if not all_chunks:
            raise ValueError("No content extracted from PDF.")

        # 4. Embed chunks
        batch_size = 32
        texts = [c["content"] for c in all_chunks]
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = embed_texts(batch)
            all_embeddings.extend(embeddings)

        # 5. Store in ChromaDB
        collection = get_or_create_collection(user_id)
        chroma_ids = [str(uuid.uuid4()) for _ in all_chunks]
        
        collection.add(
            ids=chroma_ids,
            documents=texts,
            embeddings=all_embeddings,
            metadatas=[c["metadata"] for c in all_chunks]
        )

        # 6. Store in PostgreSQL (DocumentChunk)
        pg_chunks = [
            DocumentChunk(
                user_id=user_uuid,
                source_id=source.id,
                content=chunk["content"],
                chunk_metadata=chunk["metadata"],
                chroma_id=chroma_ids[i]
            )
            for i, chunk in enumerate(all_chunks)
        ]
        db.add_all(pg_chunks)
        
        doc_record.sync_status = "success"
        await db.commit()
        print(f"[PDF] Successfully ingested {doc_record.filename} ({len(all_chunks)} chunks)")
        return len(all_chunks)

    except Exception as e:
        print(f"[PDF ERROR] Ingestion failed for {doc_record.filename}: {e}")
        doc_record.sync_status = "failed"
        if doc_record.file_metadata is None:
            doc_record.file_metadata = {}
        doc_record.file_metadata["error"] = str(e)
        await db.commit()
        raise e
    finally:
        # Cleanup the temporary file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[WARNING] Failed to delete temp file {file_path}: {e}")
