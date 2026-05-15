# Project 7: PDF Chat with RAG (Isolated)

This module is isolated under `backend/next_projects/project7_rag` and does not modify existing production routes.

## Requirements implemented
- Upload PDF and index chunks into ChromaDB.
- Use OpenAI Embeddings Large (`text-embedding-3-large`) for vector embeddings.
- Ask questions against uploaded PDF using RAG retrieval + LLM answer synthesis.

## Environment Variables
- `PROJECT7_RAG_API_KEY` (preferred)
- fallback: `LITELLM_API_KEY` or `OPENAI_API_KEY`
- `PROJECT7_RAG_BASE_URL` (optional OpenAI-compatible base URL)
- fallback: `LITELLM_PROXY_URL`
- `PROJECT7_RAG_EMBEDDING_MODEL` (default: `text-embedding-3-large`)
- `PROJECT7_RAG_CHAT_MODEL` (default: `gpt-4o-mini`)
- `PROJECT7_RAG_CHROMA_DIR` (default: use app setting `chroma_persist_dir`)

## API
- `POST /project7/rag/upload-pdf` (multipart form upload)
- `POST /project7/rag/chat`
- Legacy placeholders retained:
  - `POST /project7/rag/ingest`
  - `POST /project7/rag/query`

### Upload Example
Form fields:
- `file`: PDF file
- `document_id`: optional (auto-generated if omitted)

Response:
```json
{
  "document_id": "doc-123",
  "source_name": "my-file.pdf",
  "chunk_count": 12
}
```

### Chat Example
```json
{
  "document_id": "doc-123",
  "question": "Summarize key findings from this PDF",
  "top_k": 4
}
```

## Run Standalone
From `backend/`:
```powershell
.\.venv\Scripts\uvicorn.exe next_projects.project7_rag.app:app --host 127.0.0.1 --port 8017
```
