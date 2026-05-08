import pytest
import os
import uuid
import asyncio
import httpx
from app.main import app
from app.database import AsyncSessionLocal
from app.models.uploaded_document import UploadedDocument
from sqlalchemy import select

async def run_duplicate_test():
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # 1. Register
        email = f"test_dup_{uuid.uuid4().hex[:8]}@example.com"
        password = "password123"
        reg_res = await client.post("/auth/register", json={"email": email, "password": password, "full_name": "Test User"})
        print(f"Reg Status: {reg_res.status_code}")
        token = reg_res.json().get("access_token")
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Create a test PDF
        test_pdf_path = "tests/data/test_duplicate.pdf"
        os.makedirs("tests/data", exist_ok=True)
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "This is a duplicate test file for SHA256 hashing.")
        doc.save(test_pdf_path)
        doc.close()

        print(f"--- Uploading PDF first time ---")
        with open(test_pdf_path, "rb") as f:
            response = await client.post(
                "/ingest/pdf",
                files={"file": ("test_duplicate.pdf", f, "application/pdf")},
                headers=auth_headers
            )
        
        print(f"Status 1: {response.status_code}")
        print(f"Response 1: {response.text}")
        assert response.status_code == 200
        data1 = response.json()
        doc_id1 = data1["document_id"]
        job_id1 = data1.get("job_id")
        print(f"Doc ID 1: {doc_id1}")

        # Wait for processing
        await asyncio.sleep(3)

        print(f"--- Uploading SAME PDF again ---")
        with open(test_pdf_path, "rb") as f:
            response = await client.post(
                "/ingest/pdf",
                files={"file": ("test_duplicate_v2.pdf", f, "application/pdf")},
                headers=auth_headers
            )
        
        print(f"Status 2: {response.status_code}")
        print(f"Response 2: {response.text}")
        assert response.status_code == 200
        data2 = response.json()
        doc_id2 = data2["document_id"]
        print(f"Doc ID 2: {doc_id2}")

        # Verify in DB
        async with AsyncSessionLocal() as db:
            result1 = await db.execute(select(UploadedDocument).where(UploadedDocument.id == uuid.UUID(doc_id1)))
            doc1 = result1.scalar_one_or_none()
            print(f"Doc 1 Sync Status: {doc1.sync_status}")
            print(f"Doc 1 Hash: {doc1.file_metadata.get('hash')}")

            result2 = await db.execute(select(UploadedDocument).where(UploadedDocument.id == uuid.UUID(doc_id2)))
            doc2 = result2.scalar_one_or_none()
            print(f"Doc 2 Sync Status: {doc2.sync_status}")
            print(f"Doc 2 Hash: {doc2.file_metadata.get('hash')}")
            
            assert doc1.file_metadata.get("hash") == doc2.file_metadata.get("hash")
            assert doc2.sync_status == "success"

        # Cleanup
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)

if __name__ == "__main__":
    asyncio.run(run_duplicate_test())
