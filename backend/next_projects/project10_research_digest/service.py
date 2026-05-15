from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import arxiv
from app.ai.llm import get_async_openai_client
from app.core.config import get_settings

from .models import ResearchDigestQueryRequest, ResearchDigestResponse, ResearchPaper


def _query_terms(query: str) -> list[str]:
    return [term.strip().lower() for term in query.split() if len(term.strip()) >= 4]


def _evidence_coverage_ratio(query: str, papers: list[ResearchPaper]) -> float:
    terms = _query_terms(query)
    if not terms:
        return 1.0

    covered = 0
    for term in terms:
        if any(term in f"{paper.title} {paper.summary}".lower() for paper in papers):
            covered += 1

    return covered / len(terms)


def _has_enough_evidence(query: str, papers: list[ResearchPaper], requested_max: int) -> bool:
    if not papers:
        return False

    min_papers = min(8, max(4, requested_max // 2))
    if len(papers) < min_papers:
        return False

    current_year = datetime.now(timezone.utc).year
    recent_count = 0
    author_set: set[str] = set()
    for paper in papers:
        try:
            year = int(paper.published[:4])
            if year >= current_year - 3:
                recent_count += 1
        except (TypeError, ValueError):
            pass

        author_set.update(name.strip() for name in paper.authors if name.strip())

    coverage = _evidence_coverage_ratio(query, papers)
    return (
        recent_count >= max(2, min_papers // 2)
        and len(author_set) >= min_papers
        and coverage >= 0.5
    )


def _search_arxiv(
    query: str,
    max_results: int,
    on_progress: Callable[[dict], None] | None = None,
) -> list[ResearchPaper]:
    """Search arXiv and stop early when evidence quality is sufficient."""
    if not query.strip():
        raise ValueError('Query must not be empty.')

    papers: list[ResearchPaper] = []
    client = arxiv.Client()

    try:
        if on_progress:
            on_progress({'type': 'status', 'stage': 'searching', 'message': 'Searching arXiv...'})

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        for result in client.results(search):
            paper = ResearchPaper(
                title=result.title,
                authors=[author.name for author in result.authors],
                published=result.published.strftime('%Y-%m-%d'),
                arxiv_id=result.entry_id.split('/abs/')[-1],
                url=result.entry_id,
                summary=result.summary.replace('\n', ' ').strip(),
            )
            papers.append(paper)

            if on_progress and len(papers) % 2 == 0:
                on_progress(
                    {
                        'type': 'status',
                        'stage': 'evidence',
                        'message': f'Collected {len(papers)} papers, evaluating evidence quality...',
                    }
                )

            if _has_enough_evidence(query, papers, max_results):
                if on_progress:
                    on_progress(
                        {
                            'type': 'status',
                            'stage': 'decision',
                            'message': f'Evidence threshold reached with {len(papers)} papers.',
                        }
                    )
                break
    except Exception as exc:
        raise ValueError(f'arXiv search failed: {str(exc)}') from exc

    return papers


async def _generate_digest(papers: list[ResearchPaper], query: str, max_length: int) -> str:
    """Generate a structured research digest from papers."""
    settings = get_settings()

    if not settings.llm_model or not settings.litellm_api_key:
        # Fallback: return simple digest
        digest_lines = [
            f'Research Summary for: "{query}"',
            f'Papers Found: {len(papers)}',
            '',
            'Key Papers:',
        ]
        for i, paper in enumerate(papers[:5], 1):
            digest_lines.append(f'{i}. {paper.title} ({paper.published})')
            digest_lines.append(f'   Authors: {", ".join(paper.authors[:3])}')
        return '\n'.join(digest_lines)

    # Use LLM to generate structured digest
    papers_text = '\n\n'.join(
        [
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors)}\n"
            f"Published: {p.published}\n"
            f"Summary: {p.summary[:300]}..."
            for p in papers[:15]
        ]
    )

    client = get_async_openai_client()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {
                'role': 'system',
                'content': 'You are a research digest generator. Create a structured, concise digest of research papers. '
                'Include key findings, trends, and notable papers. Keep it under the specified length.',
            },
            {
                'role': 'user',
                'content': f'Generate a research digest for query: "{query}"\n\nPapers:\n{papers_text}\n\n'
                f'Keep digest under {max_length} characters. Format with clear sections.',
            },
        ],
    )

    digest = (response.choices[0].message.content or '').strip()
    if not digest:
        digest = f'Successfully found {len(papers)} research papers for "{query}"'

    # Truncate if needed
    if len(digest) > max_length:
        digest = digest[:max_length].rsplit(' ', 1)[0] + '...'

    return digest


async def stream_research_digest(request: ResearchDigestQueryRequest):
    """Yield streaming events for browser SSE consumption."""
    progress_events: list[dict] = []

    def _on_progress(event: dict) -> None:
        progress_events.append(event)

    yield {'type': 'status', 'stage': 'start', 'message': 'Starting research workflow...'}

    papers = _search_arxiv(request.query, request.max_results, on_progress=_on_progress)
    for event in progress_events:
        yield event

    if not papers:
        raise ValueError(f'No papers found on arXiv for query: {request.query}')

    yield {
        'type': 'status',
        'stage': 'digest',
        'message': f'Generating digest from {len(papers)} selected papers...',
    }

    digest = await _generate_digest(papers, request.query, request.max_summary_length)

    for idx in range(0, len(digest), 180):
        chunk = digest[idx : idx + 180]
        if chunk:
            yield {'type': 'token', 'content': chunk}

    result = ResearchDigestResponse(
        query=request.query,
        papers_found=len(papers),
        digest=digest,
        papers=papers,
        thread_id=request.thread_id,
    )
    yield {'type': 'final', 'result': result.model_dump()}
    yield {'type': 'done'}


async def generate_research_digest(request: ResearchDigestQueryRequest) -> ResearchDigestResponse:
    """Main entry point for research digest generation."""
    papers = _search_arxiv(request.query, request.max_results)

    if not papers:
        raise ValueError(f'No papers found on arXiv for query: {request.query}')

    digest = await _generate_digest(papers, request.query, request.max_summary_length)

    return ResearchDigestResponse(
        query=request.query,
        papers_found=len(papers),
        digest=digest,
        papers=papers,
        thread_id=request.thread_id,
    )
