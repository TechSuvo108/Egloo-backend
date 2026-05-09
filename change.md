# Changes: Google Drive Connector Implementation

I have implemented the full Google Drive connector, enabling Egloo to index and query documents from user's Google Drive accounts.

## Core Changes

### 1. OAuth Infrastructure
- **`app/services/google_oauth.py`**: Refactored to support dynamic redirect URIs. This allows separate callback handlers for Gmail and Google Drive while reusing the same client credentials.
- **`app/routers/sources.py`**: 
    - Added `GET /api/v1/sources/connect/google_drive` to initiate the OAuth flow.
    - Added `GET /api/v1/sources/callback/google_drive` to securely exchange the authorization code for tokens and store them as a new data source.
    - **Fixed Success Redirects**: Updated both Gmail and Google Drive callbacks to return `RedirectResponse(url="egloo://...")` on success, ensuring the user is returned to the app instead of seeing raw JSON.

### 2. Ingestion Pipeline
- **`app/services/fetchers/drive_fetcher.py`**: 
    - Implemented a robust fetcher for Google Drive.
    - Supports Google Docs (exported as text), PDFs (extracted using PyMuPDF), and text/markdown files.
    - Added per-page extraction logic for PDFs to improve RAG retrieval quality.
- **`app/services/ingestion_service.py`**: Integrated the Drive fetcher into the primary ingestion loop, ensuring Drive documents are chunked, embedded, and indexed in ChromaDB.

### 3. Background Processing
- **`app/workers/tasks.py`**: 
    - Added a dedicated `sync_google_drive(user_id)` task.
    - Integrated with the existing `sync_source` infrastructure to support job tracking and progress monitoring.

## Quality & Maintenance
- **Cross-Platform Compatibility**: Cleaned up print statements and logs to remove emojis, preventing `UnicodeEncodeError` on Windows systems.
- **Verification**: Created a mock-based test suite in `scratch/verify_drive.py` to validate file parsing and metadata mapping.
