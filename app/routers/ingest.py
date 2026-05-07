from typing import Union
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.ingest import IngestResponse, IngestResultResponse
from app.schemas.job import JobStatusResponse, JobListResponse
from app.schemas.document import PDFUploadAcceptedResponse, PDFUploadSuccessResponse
from app.models.uploaded_document import UploadedDocument
from app.services.source_service import get_source_by_id, get_all_sources
from app.services.ingestion_service import ingest_source
from app.services.pdf_service import process_pdf_ingestion
from app.utils.job_tracker import create_job, get_job, get_user_jobs
from app.config import settings

router = APIRouter(prefix="/ingest", tags=["ingest"])

@router.post("/trigger/{source_id}", response_model=IngestResponse)
async def trigger_ingest(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ingestion via Celery — returns immediately.
    Poll /ingest/job/{job_id} to track progress."""
    from app.workers.tasks import sync_source

    source = await get_source_by_id(db, source_id, current_user.id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.sync_status == "syncing":
        raise HTTPException(status_code=400, detail="Sync already in progress")

    job_id = str(uuid.uuid4())

    # Create job record in Redis before queuing
    await create_job(
        job_id=job_id,
        user_id=str(current_user.id),
        source_id=str(source_id),
        source_type=source.source_type,
    )

    # Queue Celery task — runs in worker container
    sync_source.delay(
        source_id=str(source_id),
        user_id=str(current_user.id),
        job_id=job_id,
    )

    return IngestResponse(
        job_id=job_id,
        source_id=source_id,
        source_type=source.source_type,
        message=f"Job queued! Poll /ingest/job/{job_id} for progress.",
    )


@router.post("/pdf", response_model=Union[PDFUploadAcceptedResponse, PDFUploadSuccessResponse])
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF file for semantic indexing.
    Validates size, type, and either processes it synchronously (free tier)
    or queues a background task (celery enabled).
    """
    import os
    from app.workers.tasks import process_pdf_task

    # 1. Validation
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Max size 20MB
    MAX_SIZE = 20 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large (Max 20MB).")
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    # 2. Save to shared storage
    storage_path = os.path.join("storage", "uploads")
    os.makedirs(storage_path, exist_ok=True)
    
    # Sanitize filename
    safe_filename = "".join([c if c.isalnum() or c in "._-" else "_" for c in file.filename])
    file_id = str(uuid.uuid4())
    temp_filename = f"{file_id}_{safe_filename}"
    full_path = os.path.abspath(os.path.join(storage_path, temp_filename))
    
    with open(full_path, "wb") as f:
        f.write(content)

    # 3. Create Document record in Postgres
    doc = UploadedDocument(
        id=uuid.UUID(file_id),
        user_id=current_user.id,
        filename=file.filename,
        sync_status="queued",
        file_metadata={"size_bytes": len(content)}
    )
    db.add(doc)
    await db.commit()

    # 4. Processing logic based on Feature Flag
    if settings.USE_ASYNC_INGEST:
        # ASYNC FLOW (Celery)
        job_id = str(uuid.uuid4())
        await create_job(
            job_id=job_id,
            user_id=str(current_user.id),
            source_id=file_id,
            source_type="pdf_upload",
        )

        process_pdf_task.delay(
            user_id=str(current_user.id),
            doc_id=file_id,
            file_path=full_path,
            job_id=job_id
        )

        return PDFUploadAcceptedResponse(
            message="PDF upload accepted and queued for processing.",
            document_id=uuid.UUID(file_id),
            job_id=job_id
        )
    else:
        # SYNC FLOW (Free Tier)
        try:
            chunks_count = await process_pdf_ingestion(
                db=db,
                user_id=str(current_user.id),
                doc_id=file_id,
                file_path=full_path
            )
            
            # Optional: trigger topic refresh in background if celery is alive but we just didn't want it for the main task
            # Or just skip it for pure sync flow.
            
            return PDFUploadSuccessResponse(
                message="PDF processed successfully",
                document_id=uuid.UUID(file_id),
                chunks_created=chunks_count
            )
        except ValueError as ve:
            raise HTTPException(
                status_code=400,
                detail=str(ve)
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"PDF processing failed: {str(e)}"
            )


@router.post("/trigger-all", response_model=list[IngestResponse])
async def trigger_all_ingest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ingestion for all connected sources at once."""
    from app.workers.tasks import sync_source

    sources = await get_all_sources(db, current_user.id)
    if not sources:
        raise HTTPException(
            status_code=404,
            detail="No sources connected. Connect Gmail, Slack, or Drive first.",
        )

    responses = []
    for source in sources:
        if source.sync_status == "syncing":
            continue

        job_id = str(uuid.uuid4())

        await create_job(
            job_id=job_id,
            user_id=str(current_user.id),
            source_id=str(source.id),
            source_type=source.source_type,
        )

        sync_source.delay(
            source_id=str(source.id),
            user_id=str(current_user.id),
            job_id=job_id,
        )

        responses.append(IngestResponse(
            job_id=job_id,
            source_id=source.id,
            source_type=source.source_type,
            message=f"Job queued for {source.source_type}!",
        ))

    return responses

@router.post("/trigger-direct/{source_id}", response_model=IngestResultResponse)
async def trigger_ingest_direct(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Synchronous ingestion — waits for full result.
    Uses request-scoped session safely because it
    completes before the response is sent.
    Use for testing only."""
    source = await get_source_by_id(db, source_id, current_user.id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.sync_status == "syncing":
        raise HTTPException(status_code=400, detail="Sync already in progress")

    try:
        result = await ingest_source(db, source, str(current_user.id))
        return IngestResultResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}",
        )

@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll this endpoint to track ingestion progress.
    Frontend polls every 2-3 seconds while status is queued or started.
    Status values: queued -> started -> success | failed
    Progress: 0 -> 10 -> 20 -> 100"""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Security: users can only see their own jobs
    if job.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    return JobStatusResponse(**job)

@router.get("/jobs", response_model=JobListResponse)
async def list_user_jobs(
    current_user: User = Depends(get_current_user),
):
    """List all recent ingestion jobs for the current user."""
    jobs = await get_user_jobs(str(current_user.id))
    return JobListResponse(
        jobs=[JobStatusResponse(**j) for j in jobs],
        total=len(jobs),
    )
