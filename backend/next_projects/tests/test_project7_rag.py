import pytest

from next_projects.project7_rag.models import RagQueryRequest
from next_projects.project7_rag.service import RagStore, RagValidationError, _chunk_text, _extract_pdf_text


def test_chunk_text_splits_large_input() -> None:
    text = 'A' * 2600
    chunks = _chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) >= 3
    assert all(chunk.strip() for chunk in chunks)


def test_extract_pdf_text_rejects_empty_payload() -> None:
    with pytest.raises(RagValidationError):
        _extract_pdf_text(b'')


@pytest.mark.asyncio
async def test_query_without_document_id_is_allowed() -> None:
    store = RagStore()

    class _CollectionStub:
        def query(self, **kwargs):
            assert kwargs.get('where') is None
            return {'documents': [[]], 'ids': [[]], 'metadatas': [[]]}

    async def _embed_stub(texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    store._get_collection = lambda: _CollectionStub()  # type: ignore[method-assign]
    store._embed_texts = _embed_stub  # type: ignore[method-assign]

    answer = await store.query(RagQueryRequest(question='What is in this file?'))
    assert 'No indexed content found' in answer.answer


@pytest.mark.asyncio
async def test_ingest_pdf_does_not_overwrite_chunks_for_same_document_id(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RagStore()

    class _CollectionStub:
        def __init__(self) -> None:
            self.calls: list[dict[str, list[str]]] = []

        def upsert(self, *, ids, documents, metadatas, embeddings) -> None:  # noqa: ANN001
            self.calls.append({'ids': list(ids), 'documents': list(documents)})

    collection = _CollectionStub()
    store._get_collection = lambda: collection  # type: ignore[method-assign]

    async def _embed_stub(texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    store._embed_texts = _embed_stub  # type: ignore[method-assign]

    def _extract_stub(_: bytes) -> tuple[str, list[tuple[int, str]]]:
        return ('First page text', [(1, 'First page text')])

    monkeypatch.setattr('next_projects.project7_rag.service._extract_pdf_text', _extract_stub)

    await store.ingest_pdf(
        source_name='a.pdf',
        pdf_bytes=b'%PDF',
        document_id='shared-doc',
        mime_type='application/pdf',
    )
    await store.ingest_pdf(
        source_name='b.pdf',
        pdf_bytes=b'%PDF',
        document_id='shared-doc',
        mime_type='application/pdf',
    )

    assert len(collection.calls) == 2
    first_ids = set(collection.calls[0]['ids'])
    second_ids = set(collection.calls[1]['ids'])
    assert first_ids
    assert second_ids
    assert first_ids.isdisjoint(second_ids)
