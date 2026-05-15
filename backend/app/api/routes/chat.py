from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatHistoryOut, ChatMessageOut, ChatStreamRequest, GeneratedImageOut
from app.services.attachment_service import build_attachment_context_async, build_attachment_image_inputs, get_attachments_by_ids
from app.services.chat_service import get_message_history, stream_chat_response
from app.services.image_generation_service import list_generated_images
from app.services.thread_service import get_thread

router = APIRouter()
_THREAD_ATTACHMENT_MEMORY: dict[tuple[str, str], list[str]] = {}


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
    generated_images = await list_generated_images(db, user_id=current_user.id, thread_id=thread_id)
    return ChatHistoryOut(
        messages=[
            ChatMessageOut(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
        generated_images=[
            GeneratedImageOut(
                id=image.id,
                thread_id=image.thread_id,
                prompt=image.prompt,
                revised_prompt=image.revised_prompt,
                mime_type=image.mime_type,
                image_base64=image.image_base64,
                created_at=image.created_at,
            )
            for image in generated_images
        ],
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

    attachment_context: str | None = None
    attachment_label: str | None = None
    attachment_image_inputs: list[dict] | None = None
    memory_key = (current_user.id, payload.thread_id)

    effective_attachment_ids: list[str] | None = payload.attachment_ids
    if payload.attachment_ids:
        effective_attachment_ids = list(dict.fromkeys(payload.attachment_ids))
        _THREAD_ATTACHMENT_MEMORY[memory_key] = effective_attachment_ids
    elif memory_key in _THREAD_ATTACHMENT_MEMORY:
        effective_attachment_ids = _THREAD_ATTACHMENT_MEMORY[memory_key]

    if effective_attachment_ids:
        attachments = await get_attachments_by_ids(
            db,
            user_id=current_user.id,
            thread_id=payload.thread_id,
            attachment_ids=effective_attachment_ids,
        )
        if payload.attachment_ids and len(attachments) != len(set(payload.attachment_ids)):
            raise HTTPException(status_code=400, detail='One or more attachments are invalid for this thread.')

        if attachments:
            _THREAD_ATTACHMENT_MEMORY[memory_key] = [item.id for item in attachments]
        elif memory_key in _THREAD_ATTACHMENT_MEMORY:
            _THREAD_ATTACHMENT_MEMORY.pop(memory_key, None)

        attachment_context = await build_attachment_context_async(attachments, user_query=payload.message)
        attachment_label = ', '.join(item.file_name for item in attachments)
        attachment_image_inputs = build_attachment_image_inputs(attachments)

    event_stream = stream_chat_response(
        db=db,
        user=current_user,
        prompt=payload.message,
        thread_id=payload.thread_id,
        attachment_context=attachment_context,
        attachment_label=attachment_label,
        attachment_image_inputs=attachment_image_inputs,
    )
    return StreamingResponse(event_stream, media_type='text/event-stream')
