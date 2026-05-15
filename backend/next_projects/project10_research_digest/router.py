import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.chat_service import save_message
from app.services.thread_service import auto_name_thread, get_thread

from .models import ResearchDigestQueryRequest, ResearchDigestResponse
from .service import generate_research_digest, stream_research_digest

router = APIRouter(prefix='/project10/research-digest', tags=['project10'])


def _format_digest_reply(result: ResearchDigestResponse) -> str:
    """Format digest response for display in chat."""
    lines = [
        '### Research Digest',
        f'Query: {result.query}',
        f'Papers Found: {result.papers_found}',
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
        lines.append(f'... and {len(result.papers) - 10} more papers')

    return '\n'.join(lines)


@router.post('/query', response_model=ResearchDigestResponse)
async def research_digest_query(
    payload: ResearchDigestQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchDigestResponse:
    """
    Generate a research digest from arXiv papers.
    
    Searches arXiv for papers matching the query and generates a structured digest.
    """
    try:
        result = await generate_research_digest(payload)

        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')

            await save_message(db, current_user.id, 'user', f'Research: {payload.query}', payload.thread_id)
            if thread.name == 'New Chat':
                await auto_name_thread(db, thread, payload.query)
            await save_message(db, current_user.id, 'assistant', _format_digest_reply(result), payload.thread_id)

        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/stream')
async def research_digest_stream(
    payload: ResearchDigestQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    async def event_generator():
        final_result: ResearchDigestResponse | None = None
        try:
            async for event in stream_research_digest(payload):
                if event.get('type') == 'final':
                    final_result = ResearchDigestResponse.model_validate(event.get('result', {}))

                yield f"data: {json.dumps(event)}\n\n"

            if payload.thread_id and final_result is not None:
                thread = await get_thread(db, payload.thread_id, current_user.id)
                if thread:
                    await save_message(db, current_user.id, 'user', f'Research: {payload.query}', payload.thread_id)
                    if thread.name == 'New Chat':
                        await auto_name_thread(db, thread, payload.query)
                    await save_message(db, current_user.id, 'assistant', _format_digest_reply(final_result), payload.thread_id)
        except ValueError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')
