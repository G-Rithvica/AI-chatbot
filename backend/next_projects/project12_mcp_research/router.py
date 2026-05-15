import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.chat_service import save_message
from app.services.thread_service import auto_name_thread, get_thread

from .models import McpResearchQueryRequest, McpResearchResponse
from .service import McpAgentError, generate_mcp_research, stream_mcp_research

router = APIRouter(prefix='/project12/mcp-research', tags=['project12'])


def _format_reply(result: McpResearchResponse) -> str:
    lines = [
        '### MCP Research Digest',
        f'Query: {result.query}',
        f'Papers Found: {result.papers_found}',
        f'Agent Source: {result.agent_source}',
        '',
        '**Digest:**',
        result.digest,
        '',
        '**Papers:**',
    ]
    for i, paper in enumerate(result.papers[:10], 1):
        lines.append(f'{i}. [{paper.title}]({paper.url})')
        if paper.authors:
            lines.append(f'   Authors: {", ".join(paper.authors[:3])}')
        lines.append(f'   Published: {paper.published}')
    if len(result.papers) > 10:
        lines.append(f'… and {len(result.papers) - 10} more papers')
    return '\n'.join(lines)


@router.post('/query', response_model=McpResearchResponse)
async def mcp_research_query(
    payload: McpResearchQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> McpResearchResponse:
    """Generate a research digest via MCP tool calls (same contract as Project 10)."""
    try:
        result = await generate_mcp_research(payload)

        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')
            await save_message(db, current_user.id, 'user', f'MCP Research: {payload.query}', payload.thread_id)
            if thread.name == 'New Chat':
                await auto_name_thread(db, thread, payload.query)
            await save_message(db, current_user.id, 'assistant', _format_reply(result), payload.thread_id)

        return result
    except McpAgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/stream')
async def mcp_research_stream(
    payload: McpResearchQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream MCP research events (same SSE event shapes as Project 10 stream)."""

    async def event_generator():
        final_result: McpResearchResponse | None = None
        try:
            async for event in stream_mcp_research(payload):
                if event.get('type') == 'final':
                    final_result = McpResearchResponse.model_validate(event.get('result', {}))
                yield f"data: {json.dumps(event)}\n\n"

            if payload.thread_id and final_result is not None:
                thread = await get_thread(db, payload.thread_id, current_user.id)
                if thread:
                    await save_message(db, current_user.id, 'user', f'MCP Research: {payload.query}', payload.thread_id)
                    if thread.name == 'New Chat':
                        await auto_name_thread(db, thread, payload.query)
                    await save_message(db, current_user.id, 'assistant', _format_reply(final_result), payload.thread_id)
        except McpAgentError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')
