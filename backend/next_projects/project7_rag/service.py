import os
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import chromadb
from openai import AsyncOpenAI
from pypdf import PdfReader

from app.core.config import get_settings
from .models import (
    RagAnswer,
    RagChatRequest,
    RagCitation,
    RagIngestRequest,
    RagPdfIngestResponse,
    RagQueryRequest,
)


class RagNotConfiguredError(RuntimeError):
    pass


class RagValidationError(ValueError):
    pass


class RagProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RagSettings:
    api_key: str | None
    base_url: str | None
    embedding_model: str
    chat_model: str
    chroma_dir: Path
    chunk_size: int
    chunk_overlap: int


def _load_settings() -> RagSettings:
    settings = get_settings()
    chroma_dir = os.getenv('PROJECT7_RAG_CHROMA_DIR') or settings.chroma_persist_dir
    chroma_path = Path(chroma_dir)
    if not chroma_path.is_absolute():
        chroma_path = Path(__file__).resolve().parents[2] / chroma_path

    return RagSettings(
        api_key=(
            os.getenv('PROJECT7_RAG_API_KEY')
            or settings.litellm_api_key
            or os.getenv('OPENAI_API_KEY')
        ),
        base_url=os.getenv('PROJECT7_RAG_BASE_URL') or settings.litellm_proxy_url,
        embedding_model=os.getenv('PROJECT7_RAG_EMBEDDING_MODEL', 'text-embedding-3-large'),
        chat_model=os.getenv('PROJECT7_RAG_CHAT_MODEL', 'gpt-4o-mini'),
        chroma_dir=chroma_path,
        chunk_size=int(os.getenv('PROJECT7_RAG_CHUNK_SIZE', '1200')),
        chunk_overlap=int(os.getenv('PROJECT7_RAG_CHUNK_OVERLAP', '200')),
    )


def _build_openai_client(settings: RagSettings) -> AsyncOpenAI:
    if not settings.api_key:
        raise RagNotConfiguredError(
            'PROJECT7_RAG_API_KEY (or LITELLM_API_KEY / OPENAI_API_KEY) is required for Project 7 RAG.'
        )

    kwargs: dict[str, Any] = {'api_key': settings.api_key}
    if settings.base_url:
        kwargs['base_url'] = settings.base_url
    return AsyncOpenAI(**kwargs)


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if not cleaned:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    chunks: list[str] = []
    start = 0
    length = len(cleaned)

    while start < length:
        end = min(length, start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = max(end - overlap, start + 1)

    return chunks


def _extract_pdf_text(pdf_bytes: bytes) -> tuple[str, list[tuple[int, str]]]:
    if not pdf_bytes:
        raise RagValidationError('Uploaded PDF is empty.')

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:  # noqa: BLE001
        raise RagValidationError(f'Failed to read PDF: {exc}') from exc

    page_texts: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or '').strip()
        if page_text:
            page_texts.append((index, page_text))

    if not page_texts:
        raise RagValidationError('No extractable text found in the PDF.')

    full_text = '\n\n'.join(text for _, text in page_texts)
    return full_text, page_texts


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _parse_document_filter(document_id: str | None) -> list[str] | None:
    if document_id is None:
        return None

    raw = document_id.strip()
    if not raw:
        return None

    if raw in {'*'} or raw.lower() == 'all':
        return None

    values = [item.strip() for item in raw.split(',') if item.strip()]
    if not values:
        return None

    # Preserve order but deduplicate to avoid oversized where filters.
    unique_values = list(dict.fromkeys(values))
    return unique_values


class RagStore:
    """Project 7 RAG store backed by ChromaDB and OpenAI embeddings."""

    def __init__(self) -> None:
        self._collection_name = 'project7_rag_pdf'

    def _get_collection(self):
        settings = _load_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        collection = client.get_or_create_collection(name=self._collection_name)
        return collection

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        settings = _load_settings()
        client = _build_openai_client(settings)
        try:
            response = await client.embeddings.create(model=settings.embedding_model, input=texts)
        except Exception as exc:  # noqa: BLE001
            raise RagProviderError(f'Embedding request failed: {exc}') from exc

        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts):
            raise RagProviderError('Embedding response size mismatch.')
        return vectors

    async def ingest_pdf(
        self,
        *,
        source_name: str,
        pdf_bytes: bytes,
        document_id: str | None,
        mime_type: str | None,
    ) -> RagPdfIngestResponse:
        if mime_type and mime_type != 'application/pdf' and not source_name.lower().endswith('.pdf'):
            raise RagValidationError('Only PDF uploads are supported for Project 7.')

        resolved_document_id = (document_id or str(uuid.uuid4())).strip()
        if not resolved_document_id:
            raise RagValidationError('document_id cannot be empty.')

        _, page_texts = _extract_pdf_text(pdf_bytes)
        settings = _load_settings()

        chunk_texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        chunk_index = 0
        ingest_run_id = uuid.uuid4().hex
        for page_number, page_text in page_texts:
            page_chunks = _chunk_text(page_text, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
            for chunk in page_chunks:
                chunk_id = f'{resolved_document_id}:{ingest_run_id}:{chunk_index}'
                ids.append(chunk_id)
                chunk_texts.append(chunk)
                metadatas.append(
                    {
                        'document_id': resolved_document_id,
                        'source_name': source_name,
                        'chunk_id': chunk_id,
                        'page_number': page_number,
                    }
                )
                chunk_index += 1

        if not chunk_texts:
            raise RagValidationError('No text chunks could be generated from PDF.')

        embeddings = await self._embed_texts(chunk_texts)
        collection = self._get_collection()
        collection.upsert(ids=ids, documents=chunk_texts, metadatas=metadatas, embeddings=embeddings)

        return RagPdfIngestResponse(
            document_id=resolved_document_id,
            source_name=source_name,
            chunk_count=len(chunk_texts),
        )

    async def ingest(self, request: RagIngestRequest) -> None:
        if not request.content.strip():
            raise RagValidationError('content cannot be empty.')

        settings = _load_settings()
        chunks = _chunk_text(request.content, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
        if not chunks:
            raise RagValidationError('No chunks produced from content.')

        ids = [f'{request.document_id}:{idx}' for idx in range(len(chunks))]
        metadatas = [
            {
                'document_id': request.document_id,
                'source_name': request.source_name,
                'chunk_id': ids[idx],
                'page_number': 1,
            }
            for idx in range(len(chunks))
        ]
        embeddings = await self._embed_texts(chunks)
        collection = self._get_collection()
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)

    async def chat(self, request: RagChatRequest) -> RagAnswer:
        return await self.query(
            RagQueryRequest(
                document_id=request.document_id,
                question=request.question,
                top_k=request.top_k,
            )
        )

    async def query(self, request: RagQueryRequest) -> RagAnswer:
        document_ids = _parse_document_filter(request.document_id)
        collection = self._get_collection()

        question_embedding = await self._embed_texts([request.question])
        query_kwargs: dict[str, Any] = {
            'query_embeddings': question_embedding,
            'n_results': request.top_k,
        }
        if document_ids:
            if len(document_ids) == 1:
                query_kwargs['where'] = {'document_id': document_ids[0]}
            else:
                query_kwargs['where'] = {'document_id': {'$in': document_ids}}

        try:
            query_result = collection.query(**query_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RagProviderError(f'Chroma query failed: {exc}') from exc

        docs_nested = _as_list(query_result.get('documents'))
        ids_nested = _as_list(query_result.get('ids'))
        metas_nested = _as_list(query_result.get('metadatas'))

        docs = docs_nested[0] if docs_nested else []
        ids = ids_nested[0] if ids_nested else []
        metas = metas_nested[0] if metas_nested else []

        citations: list[RagCitation] = []
        context_parts: list[str] = []
        default_document_id = document_ids[0] if document_ids and len(document_ids) == 1 else 'unknown'

        for idx, snippet in enumerate(docs[: request.top_k]):
            meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
            chunk_id = ids[idx] if idx < len(ids) else f'{default_document_id}:{idx}'
            page_number = meta.get('page_number') if isinstance(meta, dict) else None
            source_name = meta.get('source_name') if isinstance(meta, dict) else None
            citation_document_id = meta.get('document_id') if isinstance(meta, dict) else None

            citations.append(
                RagCitation(
                    document_id=str(citation_document_id) if citation_document_id else default_document_id,
                    chunk_id=str(chunk_id),
                    snippet=str(snippet)[:300],
                    source_name=str(source_name) if source_name else None,
                    page_number=int(page_number) if isinstance(page_number, int) else None,
                )
            )
            context_parts.append(f'[{idx + 1}] {snippet}')

        if not context_parts:
            if document_ids:
                return RagAnswer(answer='No indexed content found for the provided document_id filter.', citations=[])
            return RagAnswer(answer='No indexed content found. Upload one or more PDFs first.', citations=[])

        settings = _load_settings()
        client = _build_openai_client(settings)

        prompt = (
            'You are a RAG assistant. Answer using only the provided context. '
            'If context is insufficient, say that clearly. '
            'Keep the answer concise and factual.\n\n'
            f'Question: {request.question}\n\n'
            'Context:\n'
            + '\n\n'.join(context_parts)
        )

        try:
            response = await client.chat.completions.create(
                model=settings.chat_model,
                messages=[
                    {'role': 'system', 'content': 'You answer questions grounded in retrieved document chunks.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            raise RagProviderError(f'Chat completion request failed: {exc}') from exc

        answer_text = ''
        if response.choices:
            message = response.choices[0].message
            answer_text = (message.content or '').strip()
        if not answer_text:
            answer_text = 'I could not generate an answer from the retrieved context.'

        return RagAnswer(answer=answer_text, citations=citations)


rag_store = RagStore()
