from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .models import RagAnswer, RagChatRequest, RagIngestRequest, RagPdfIngestResponse, RagQueryRequest
from .service import RagNotConfiguredError, RagProviderError, RagValidationError, rag_store

router = APIRouter(prefix='/project7/rag', tags=['project7'])


@router.post('/ingest', status_code=202)
async def ingest(payload: RagIngestRequest) -> dict[str, str]:
    try:
        await rag_store.ingest(payload)
    except RagValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RagNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RagProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {'status': 'accepted'}


@router.post('/upload-pdf', response_model=RagPdfIngestResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    document_id: str | None = Form(default=None),
) -> RagPdfIngestResponse:
    try:
        data = await file.read()
        return await rag_store.ingest_pdf(
            source_name=file.filename or 'uploaded.pdf',
            pdf_bytes=data,
            document_id=document_id,
            mime_type=file.content_type,
        )
    except RagValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RagNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RagProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/chat', response_model=RagAnswer)
async def chat(payload: RagChatRequest) -> RagAnswer:
    try:
        return await rag_store.chat(payload)
    except RagValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RagNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RagProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/query', response_model=RagAnswer)
async def query(payload: RagQueryRequest) -> RagAnswer:
    try:
        return await rag_store.query(payload)
    except RagValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RagNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RagProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
