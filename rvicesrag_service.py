[35mREADME.md[m[36m:[m    "[1;31mchroma[m": "connected",
[35malembic/versions/07cd006bfa9c_initial_tables.py[m[36m:[m    sa.Column('[1;31mchroma[m_id', sa.String(), nullable=True),
[35mapp/ai/rag_service.py[m[36m:[mfrom app.utils.[1;31mchroma[m_client import get_or_create_collection
[35mapp/main.py[m[36m:[m        from app.utils.[1;31mchroma[m_client import get_[1;31mchroma[m_client
[35mapp/main.py[m[36m:[m        client = get_[1;31mchroma[m_client()
[35mapp/main.py[m[36m:[m        from app.utils.[1;31mchroma[m_client import get_[1;31mchroma[m_client
[35mapp/main.py[m[36m:[m        get_[1;31mchroma[m_client().heartbeat()
[35mapp/main.py[m[36m:[m        results["[1;31mchroma[m"] = "connected"
[35mapp/main.py[m[36m:[m        results["[1;31mchroma[m"] = f"unavailable: {str(e)[:60]}"
[35mapp/models/document_chunk.py[m[36m:[m    [1;31mchroma[m_id = Column(String, nullable=True)
[35mapp/services/ingestion_service.py[m[36m:[mfrom app.utils.[1;31mchroma[m_client import get_or_create_collection
[35mapp/services/ingestion_service.py[m[36m:[m        [1;31mchroma[m_ids = [str(uuid.uuid4()) for _ in all_chunks]
[35mapp/services/ingestion_service.py[m[36m:[m            ids=[1;31mchroma[m_ids,
[35mapp/services/ingestion_service.py[m[36m:[m        print(f"✅ Stored {len([1;31mchroma[m_ids)} vectors in ChromaDB")
[35mapp/services/ingestion_service.py[m[36m:[m                [1;31mchroma[m_id=[1;31mchroma[m_ids[i],
[35mapp/services/ingestion_service.py[m[36m:[m            "vectors_stored": len([1;31mchroma[m_ids),
[35mapp/services/pdf_service.py[m[36m:[mfrom app.utils.[1;31mchroma[m_client import get_or_create_collection
[35mapp/services/pdf_service.py[m[36m:[m        [1;31mchroma[m_ids = [str(uuid.uuid4()) for _ in all_chunks]
[35mapp/services/pdf_service.py[m[36m:[m            ids=[1;31mchroma[m_ids,
[35mapp/services/pdf_service.py[m[36m:[m                [1;31mchroma[m_id=[1;31mchroma[m_ids[i]
[35mapp/utils/chroma_client.py[m[36m:[mimport [1;31mchroma[mdb
[35mapp/utils/chroma_client.py[m[36m:[mdef get_[1;31mchroma[m_client() -> [1;31mchroma[mdb.HttpClient:
[35mapp/utils/chroma_client.py[m[36m:[m        _client = [1;31mchroma[mdb.HttpClient(
[35mapp/utils/chroma_client.py[m[36m:[mdef get_or_create_collection(user_id: str) -> [1;31mchroma[mdb.Collection:
[35mapp/utils/chroma_client.py[m[36m:[m    client = get_[1;31mchroma[m_client()
[35mdocker-compose.yml[m[36m:[m  [1;31mchroma[m:
[35mdocker-compose.yml[m[36m:[m    image: [1;31mchroma[mdb/[1;31mchroma[m:latest
[35mdocker-compose.yml[m[36m:[m      - [1;31mchroma[m_data:/[1;31mchroma[m/[1;31mchroma[m
[35mdocker-compose.yml[m[36m:[m      - CHROMA_HOST=[1;31mchroma[m
[35mdocker-compose.yml[m[36m:[m      [1;31mchroma[m:
[35mdocker-compose.yml[m[36m:[m      - CHROMA_HOST=[1;31mchroma[m
[35mdocker-compose.yml[m[36m:[m  [1;31mchroma[m_data:
[35mrequirements.txt[m[36m:[m[1;31mchroma[mdb
