import pytest

import next_projects.project10_research_digest.service as project10_service
from next_projects.project10_research_digest.models import ResearchDigestQueryRequest, ResearchPaper


def _paper(index: int, year: int = 2024) -> ResearchPaper:
    return ResearchPaper(
        title=f'Transformer Study {index}',
        authors=[f'Author {index}', f'Collaborator {index}'],
        published=f'{year}-01-01',
        arxiv_id=f'1234.{index:05d}',
        url=f'https://arxiv.org/abs/1234.{index:05d}',
        summary='A transformer model for sequence analysis and retrieval.',
    )


def test_search_arxiv_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match='Query must not be empty'):
        project10_service._search_arxiv('', max_results=5)


def test_has_enough_evidence_true_for_diverse_recent_set() -> None:
    papers = [_paper(i, year=2024 if i % 2 else 2023) for i in range(1, 7)]
    assert project10_service._has_enough_evidence('transformer retrieval', papers, 10) is True


def test_has_enough_evidence_false_for_small_set() -> None:
    papers = [_paper(1), _paper(2), _paper(3)]
    assert project10_service._has_enough_evidence('transformer retrieval', papers, 10) is False


@pytest.mark.asyncio
async def test_generate_research_digest_uses_search_and_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _digest_stub(papers: list[ResearchPaper], query: str, max_length: int) -> str:
        assert query == 'transformer agents'
        assert max_length == 700
        assert len(papers) == 5
        return 'Structured digest output'

    monkeypatch.setattr(
        project10_service,
        '_search_arxiv',
        lambda query, max_results, on_progress=None: [_paper(i) for i in range(1, 6)],
    )
    monkeypatch.setattr(project10_service, '_generate_digest', _digest_stub)

    result = await project10_service.generate_research_digest(
        ResearchDigestQueryRequest(query='transformer agents', max_results=10, max_summary_length=700)
    )

    assert result.papers_found == 5
    assert result.digest == 'Structured digest output'
    assert result.query == 'transformer agents'


@pytest.mark.asyncio
async def test_stream_research_digest_emits_final_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _digest_stub(papers: list[ResearchPaper], query: str, max_length: int) -> str:
        return 'Digest chunk A. Digest chunk B.'

    monkeypatch.setattr(
        project10_service,
        '_search_arxiv',
        lambda query, max_results, on_progress=None: [_paper(i) for i in range(1, 5)],
    )
    monkeypatch.setattr(project10_service, '_generate_digest', _digest_stub)

    events: list[dict] = []
    async for event in project10_service.stream_research_digest(
        ResearchDigestQueryRequest(query='transformer', max_results=8)
    ):
        events.append(event)

    assert any(event.get('type') == 'status' for event in events)
    assert any(event.get('type') == 'token' for event in events)
    assert any(event.get('type') == 'final' for event in events)
    assert events[-1].get('type') == 'done'
