"""
Project 12 — MCP Research Server
=================================
Exposes two MCP tools backed by the same arXiv search and LLM digest logic
as Project 10. The server is instantiated **in-process** using FastMCP so no
additional port is required.  The Project-12 agent calls the tools through the
MCP protocol layer; Project 10's own routes are never touched.

Tool catalogue
--------------
search_arxiv_papers(query, max_results)  →  JSON list of paper objects
generate_research_digest(papers_json, query, max_length)  →  digest string
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import arxiv
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name='research-server')


# ---------------------------------------------------------------------------
# Helpers (pure; no shared state)
# ---------------------------------------------------------------------------

def _query_terms(query: str) -> list[str]:
    return [t.strip().lower() for t in query.split() if len(t.strip()) >= 4]


def _evidence_coverage_ratio(query: str, papers: list[dict]) -> float:
    terms = _query_terms(query)
    if not terms:
        return 1.0
    covered = sum(
        1 for term in terms
        if any(term in f"{p.get('title', '')} {p.get('summary', '')}".lower() for p in papers)
    )
    return covered / len(terms)


def _has_enough_evidence(query: str, papers: list[dict], requested_max: int) -> bool:
    if not papers:
        return False
    min_papers = min(8, max(4, requested_max // 2))
    if len(papers) < min_papers:
        return False
    current_year = datetime.now(timezone.utc).year
    recent_count = 0
    author_set: set[str] = set()
    for p in papers:
        try:
            if int(p['published'][:4]) >= current_year - 3:
                recent_count += 1
        except (ValueError, KeyError):
            pass
        for name in p.get('authors', []):
            if name.strip():
                author_set.add(name.strip())
    coverage = _evidence_coverage_ratio(query, papers)
    return (
        recent_count >= max(2, min_papers // 2)
        and len(author_set) >= min_papers
        and coverage >= 0.5
    )


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_arxiv_papers(query: str, max_results: int = 10) -> str:
    """Search arXiv for recent papers matching *query*.

    Args:
        query: Free-text search query.
        max_results: Upper bound on papers to retrieve (1–50).

    Returns:
        JSON-encoded list of paper objects with keys:
        title, authors, published, arxiv_id, url, summary.
    """
    if not query.strip():
        raise ValueError('query must not be empty.')
    max_results = max(1, min(50, max_results))

    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers: list[dict] = []
    for result in client.results(search):
        paper = {
            'title': result.title,
            'authors': [a.name for a in result.authors],
            'published': result.published.strftime('%Y-%m-%d'),
            'arxiv_id': result.entry_id.split('/abs/')[-1],
            'url': result.entry_id,
            'summary': result.summary.replace('\n', ' ').strip(),
        }
        papers.append(paper)

    return json.dumps(papers)


@mcp.tool()
async def generate_research_digest(papers_json: str, query: str, max_length: int = 800) -> str:
    """Generate a structured research digest from a JSON list of papers.

    Args:
        papers_json: JSON string produced by search_arxiv_papers.
        query: Original search query used for context.
        max_length: Maximum character length for the digest.

    Returns:
        Digest text summarising findings, trends, and notable papers.
    """
    from app.ai.llm import get_async_openai_client
    from app.core.config import get_settings

    try:
        papers: list[dict] = json.loads(papers_json)
    except json.JSONDecodeError as exc:
        raise ValueError('papers_json must be a valid JSON string.') from exc

    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        # Fallback: plain text digest
        lines = [f'Research Summary for: "{query}"', f'Papers Found: {len(papers)}', '', 'Key Papers:']
        for i, p in enumerate(papers[:5], 1):
            lines.append(f'{i}. {p["title"]} ({p["published"]})')
            lines.append(f'   Authors: {", ".join(p.get("authors", [])[:3])}')
        return '\n'.join(lines)

    papers_text = '\n\n'.join(
        f"Title: {p['title']}\n"
        f"Authors: {', '.join(p.get('authors', []))}\n"
        f"Published: {p['published']}\n"
        f"Summary: {p.get('summary', '')[:300]}..."
        for p in papers[:15]
    )

    client = get_async_openai_client()
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are a research digest generator. Create a structured, concise digest of '
                    'research papers. Include key findings, trends, and notable papers. '
                    'Keep it under the specified length.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'Generate a research digest for query: "{query}"\n\nPapers:\n{papers_text}\n\n'
                    f'Keep digest under {max_length} characters. Format with clear sections.'
                ),
            },
        ],
    )
    digest = (response.choices[0].message.content or '').strip()
    if not digest:
        digest = f'Successfully found {len(papers)} research papers for "{query}"'
    if len(digest) > max_length:
        digest = digest[:max_length].rsplit(' ', 1)[0] + '...'
    return digest
