import io
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List

import docx
import fitz  # PyMuPDF
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def _build_drive_service(access_token: str, refresh_token: str = None):
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("drive", "v3", credentials=creds)


def _extract_text_from_docx(content: bytes) -> str:
    """Extract text from a .docx file bytes."""
    try:
        doc = docx.Document(BytesIO(content))
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        print(f"[Drive] Failed to extract docx text: {e}")
        return ""


def _extract_text_from_pdf(content: bytes) -> str:
    """Extract text from a PDF file bytes using PyMuPDF."""
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            if doc.is_encrypted:
                print("[Drive] PDF is encrypted, skipping.")
                return ""
            text = ""
            for page in doc:
                text += page.get_text()
            return text
    except Exception as e:
        print(f"[Drive] Failed to extract PDF text: {e}")
        return ""


def fetch_drive_files(
    access_token: str,
    refresh_token: str = None,
    days_back: int = 30,
    max_files: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch and parse files from Google Drive modified in last N days.
    Supports: Google Docs (exported as txt), .docx, .pdf, .txt files.

    Each dict:
    {
        "document_id": "drive_<file_id>",
        "source_type": "google_drive",
        "title": "filename",
        "timestamp": "ISO string",
        "content": "extracted plain text",
    }
    """
    service = _build_drive_service(access_token, refresh_token)

    after_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    after_str = after_date.strftime("%Y-%m-%dT%H:%M:%S")

    # Fetch files modified recently
    query = (
        f"modifiedTime > '{after_str}' "
        "and trashed = false "
        "and ("
        "  mimeType = 'application/vnd.google-apps.document' or "
        "  mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or "
        "  mimeType = 'application/pdf' or "
        "  mimeType = 'text/plain' or "
        "  mimeType = 'text/markdown'"
        ")"
    )

    results = (
        service.files()
        .list(
            q=query,
            pageSize=100,
            fields="files(id, name, mimeType, modifiedTime)",
        )
        .execute()
    )

    files = results.get("files", [])
    parsed_files = []

    for file in files:
        file_id = file["id"]
        file_name = file["name"]
        mime_type = file["mimeType"]
        modified_time = file.get("modifiedTime", datetime.now(timezone.utc).isoformat())

        try:
            content_text = ""

            if mime_type == "application/vnd.google-apps.document":
                # Export Google Doc as plain text
                export = (
                    service.files()
                    .export(
                        fileId=file_id,
                        mimeType="text/plain",
                    )
                    .execute()
                )
                content_text = export.decode("utf-8", errors="ignore")

            else:
                # Download binary file
                request = service.files().get_media(fileId=file_id)
                buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                file_bytes = buffer.getvalue()

                if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    content_text = _extract_text_from_docx(file_bytes)
                elif mime_type == "application/pdf":
                    content_text = _extract_text_from_pdf(file_bytes)
                elif mime_type == "text/plain":
                    content_text = file_bytes.decode("utf-8", errors="ignore")

            content_text = content_text.strip()
            if not content_text:
                continue

            parsed_files.append({
                "document_id": f"drive_{file_id}",
                "source_type": "google_drive",
                "title": file_name,
                "timestamp": modified_time,
                "content": f"Document: {file_name}\n\n{content_text}",
            })

        except Exception as e:
            print(f"Failed to process Drive file {file_name}: {e}")
            continue

    print(f"Google Drive: fetched {len(parsed_files)} files")
    return parsed_files
