"""
Project 12 — MCP Agent Service
================================
The agent orchestrates the research workflow by calling MCP tools instead of
the hand-written helper functions used in Project 10.

Call chain:
  McpResearchQueryRequest
    → agent calls MCP tool: search_arxiv_papers(query, max_results)
    → agent calls MCP tool: generate_research_digest(papers_json, query, max_length)
    → returns McpResearchResponse / streams events

The FastAPI router and the frontend send the same request/response shape as
Project 10 so no frontend code needs to change.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from .models import McpResearchPaper, McpResearchQueryRequest, McpResearchResponse
from .mcp_server import mcp


class McpAgentError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Internal: call MCP tools in-process via the registered tool functions
# ---------------------------------------------------------------------------

def _get_tool(name: str):
    """Retrieve a tool function from the FastMCP server registry."""
    for tool in mcp._tool_manager._tools.values():  # noqa: SLF001
        if tool.name == name:
            return tool.fn
    raise McpAgentError(f'MCP tool "{name}" not registered in research-server.')


async def _call_search(query: str, max_results: int) -> list[dict]:
    fn = _get_tool('search_arxiv_papers')
    raw = fn(query=query, max_results=max_results)
    return json.loads(raw)


async def _call_digest(papers: list[dict], query: str, max_length: int) -> str:
    fn = _get_tool('generate_research_digest')
    papers_json = json.dumps(papers)
    import asyncio, inspect  # noqa: E401
    if inspect.iscoroutinefunction(fn):
        return await fn(papers_json=papers_json, query=query, max_length=max_length)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(papers_json=papers_json, query=query, max_length=max_length))


def _to_model_papers(raw: list[dict]) -> list[McpResearchPaper]:
    return [
        McpResearchPaper(
            title=p['title'],
            authors=p.get('authors', []),
            published=p['published'],
            arxiv_id=p.get('arxiv_id', ''),
            url=p.get('url', ''),
            summary=p.get('summary', ''),
        )
        for p in raw
    ]


# ---------------------------------------------------------------------------
# Public API — mirrors project10/service.py signatures
# ---------------------------------------------------------------------------

async def generate_mcp_research(request: McpResearchQueryRequest) -> McpResearchResponse:
    """Invoke MCP tools synchronously and return a complete response object."""
    raw_papers = await _call_search(request.query, request.max_results)
    if not raw_papers:
        raise McpAgentError(f'No papers found on arXiv for query: {request.query}')

    digest = await _call_digest(raw_papers, request.query, request.max_summary_length)
    papers = _to_model_papers(raw_papers)

    return McpResearchResponse(
        query=request.query,
        papers_found=len(papers),
        digest=digest,
        papers=papers,
        thread_id=request.thread_id,
        agent_source='mcp',
    )


async def stream_mcp_research(request: McpResearchQueryRequest) -> AsyncIterator[dict]:
    """Yield SSE-style event dicts — same event types as Project 10 stream."""
    yield {'type': 'status', 'stage': 'start', 'message': '[MCP] Research agent starting…'}

    yield {'type': 'status', 'stage': 'tool_call', 'message': '[MCP] Calling tool: search_arxiv_papers'}
    try:
        raw_papers = await _call_search(request.query, request.max_results)
    except Exception as exc:
        raise McpAgentError(f'MCP tool search_arxiv_papers failed: {exc}') from exc

    if not raw_papers:
        raise McpAgentError(f'No papers found on arXiv for query: {request.query}')

    yield {
        'type': 'status',
        'stage': 'evidence',
        'message': f'[MCP] search_arxiv_papers returned {len(raw_papers)} papers.',
    }

    yield {
        'type': 'status',
        'stage': 'tool_call',
        'message': '[MCP] Calling tool: generate_research_digest',
    }
    try:
        digest = await _call_digest(raw_papers, request.query, request.max_summary_length)
    except Exception as exc:
        raise McpAgentError(f'MCP tool generate_research_digest failed: {exc}') from exc

    for idx in range(0, len(digest), 180):
        chunk = digest[idx : idx + 180]
        if chunk:
            yield {'type': 'token', 'content': chunk}

    papers = _to_model_papers(raw_papers)
    result = McpResearchResponse(
        query=request.query,
        papers_found=len(papers),
        digest=digest,
        papers=papers,
        thread_id=request.thread_id,
        agent_source='mcp',
    )
    yield {'type': 'final', 'result': result.model_dump()}
    yield {'type': 'done'}
