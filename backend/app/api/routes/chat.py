from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatHistoryOut, ChatMessageOut, ChatStreamRequest
from app.services.chat_service import get_message_history, stream_chat_response
from app.services.thread_service import get_thread

router = APIRouter()


@router.get('/history', response_model=ChatHistoryOut)
async def history(
    thread_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatHistoryOut:
    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')
    messages = await get_message_history(db, current_user.id, thread_id=thread_id)
    return ChatHistoryOut(
        messages=[
            ChatMessageOut(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ]
    )


@router.post('/stream')
async def stream_chat(
    payload: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    thread = await get_thread(db, payload.thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail='Thread not found.')
    event_stream = stream_chat_response(db=db, user=current_user, prompt=payload.message, thread_id=payload.thread_id)
    return StreamingResponse(event_stream, media_type='text/event-stream')
