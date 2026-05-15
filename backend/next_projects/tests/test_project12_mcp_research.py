"""
Deterministic tests for Project 12 — MCP Research Agent.
All external calls (arXiv, LLM) are monkeypatched; no network required.
"""
from __future__ import annotations

import json
import pytest

import next_projects.project12_mcp_research.service as p12_service
import next_projects.project12_mcp_research.mcp_server as mcp_module
from next_projects.project12_mcp_research.models import McpResearchQueryRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_papers(n: int = 4) -> list[dict]:
    return [
        {
            'title': f'Transformer Study {i}',
            'authors': [f'Author {i}', f'Collaborator {i}'],
            'published': '2024-01-01',
            'arxiv_id': f'1234.{i:05d}',
            'url': f'https://arxiv.org/abs/1234.{i:05d}',
            'summary': 'A transformer model for sequence analysis.',
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# MCP tool: search_arxiv_papers
# ---------------------------------------------------------------------------

def test_search_arxiv_rejects_empty_query() -> None:
    fn = p12_service._get_tool('search_arxiv_papers')
    with pytest.raises(ValueError, match='must not be empty'):
        fn(query='', max_results=5)


def test_search_arxiv_caps_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_results is silently clamped to [1, 50]."""
    called_with: list[int] = []

    import arxiv as arxiv_mod

    class _FakeClient:
        def results(self, search):
            called_with.append(search.max_results)
            return iter([])

    monkeypatch.setattr(mcp_module, 'arxiv', type('_M', (), {'Client': _FakeClient, 'Search': arxiv_mod.Search,
                                                               'SortCriterion': arxiv_mod.SortCriterion,
                                                               'SortOrder': arxiv_mod.SortOrder})())

    fn = p12_service._get_tool('search_arxiv_papers')
    fn(query='transformers', max_results=200)   # should clamp to 50
    assert called_with[0] == 50


# ---------------------------------------------------------------------------
# MCP tool: generate_research_digest (fallback when LLM not configured)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_digest_fallback_no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LLM is not configured, a plain-text digest is returned."""
    import app.core.config as _config_mod

    class _NoLLMSettings:
        llm_model = None
        litellm_api_key = None

    monkeypatch.setattr(_config_mod, 'get_settings', lambda: _NoLLMSettings())

    fn = p12_service._get_tool('generate_research_digest')
    papers_json = json.dumps(_fake_papers(3))

    # Call the underlying async function directly
    import asyncio
    import inspect
    if inspect.iscoroutinefunction(fn):
        result = await fn(papers_json=papers_json, query='transformers', max_length=500)
    else:
        result = fn(papers_json=papers_json, query='transformers', max_length=500)

    # We accept any non-empty string output
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Service: generate_mcp_research (end-to-end with stubs)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_mcp_research_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _fake_papers(4)

    async def _fake_call_search(query, max_results):
        return raw

    async def _fake_call_digest(papers, query, max_length):
        return 'Digest summary for testing.'

    monkeypatch.setattr(p12_service, '_call_search', _fake_call_search)
    monkeypatch.setattr(p12_service, '_call_digest', _fake_call_digest)

    request = McpResearchQueryRequest(query='transformers', max_results=10)
    result = await p12_service.generate_mcp_research(request)

    assert result.query == 'transformers'
    assert result.papers_found == 4
    assert result.digest == 'Digest summary for testing.'
    assert result.agent_source == 'mcp'


@pytest.mark.asyncio
async def test_generate_mcp_research_raises_when_no_papers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_papers(query, max_results):
        return []

    monkeypatch.setattr(p12_service, '_call_search', _no_papers)

    with pytest.raises(p12_service.McpAgentError, match='No papers found'):
        await p12_service.generate_mcp_research(
            McpResearchQueryRequest(query='nonexistent topic xyz', max_results=5)
        )


# ---------------------------------------------------------------------------
# Service: stream_mcp_research
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_mcp_research_emits_correct_event_types(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_search(query, max_results):
        return _fake_papers(3)

    async def _fake_call_digest(papers, query, max_length):
        return 'Short digest.'

    monkeypatch.setattr(p12_service, '_call_search', _fake_call_search)
    monkeypatch.setattr(p12_service, '_call_digest', _fake_call_digest)

    events: list[dict] = []
    async for evt in p12_service.stream_mcp_research(McpResearchQueryRequest(query='ai agents')):
        events.append(evt)

    types = [e['type'] for e in events]
    assert 'status' in types
    assert 'token' in types
    assert 'final' in types
    assert events[-1]['type'] == 'done'

    final_evt = next(e for e in events if e['type'] == 'final')
    assert final_evt['result']['agent_source'] == 'mcp'
