import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chains import stream_chain_tokens
from app.ai.memory import build_memory_window
from app.core.config import get_settings
from app.models.message import Message
from app.models.n8n_webhook_event import N8nWebhookEvent
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)


def _extract_forced_attachment_heading(attachment_context: str | None, prompt: str) -> str | None:
    if not attachment_context:
        return None

    prompt_lower = prompt.lower()
    if not any(keyword in prompt_lower for keyword in ('title', 'heading', 'name')):
        return None

    marker = 'Exact matched heading for the requested section:'
    marker_index = attachment_context.find(marker)
    if marker_index < 0:
        return None

    remainder = attachment_context[marker_index + len(marker):].strip()
    if not remainder:
        return None

    heading = remainder.splitlines()[0].strip()
    return heading or None


async def save_message(db: AsyncSession, user_id: str, role: str, content: str, thread_id: str | None = None) -> Message:
    message = Message(user_id=user_id, role=role, content=content, thread_id=thread_id)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_message_history(db: AsyncSession, user_id: str, limit: int = 100, thread_id: str | None = None) -> list[Message]:
    stmt = select(Message).where(Message.user_id == user_id)
    if thread_id is not None:
        stmt = stmt.where(Message.thread_id == thread_id)
    stmt = stmt.order_by(Message.created_at.asc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def stream_chat_response(
    db: AsyncSession,
    user: User,
    prompt: str,
    thread_id: str | None = None,
    attachment_context: str | None = None,
    attachment_label: str | None = None,
    attachment_image_inputs: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[str, None]:
    if not settings.llm_model:
        yield _sse_error('LLM_MODEL is not configured.')
        return

    await _trigger_n8n_sidecar(db=db, user=user, prompt=prompt, thread_id=thread_id)

    prompt_for_storage = prompt
    if attachment_label:
        prompt_for_storage = f"{prompt}\n\n[Attached files: {attachment_label}]"

    await save_message(db, user.id, 'user', prompt_for_storage, thread_id)

    forced_heading = _extract_forced_attachment_heading(attachment_context, prompt)
    if forced_heading:
        response_for_storage = forced_heading
        if attachment_label:
            response_for_storage = f"{response_for_storage}\n\n[Used files: {attachment_label}]"

        await save_message(db, user.id, 'assistant', response_for_storage, thread_id)
        yield _sse_data({'type': 'token', 'content': forced_heading})
        yield _sse_data({'type': 'done'})
        return

    # Auto-name thread on first message
    if thread_id:
        from app.models.thread import Thread
        from app.services.thread_service import auto_name_thread
        from sqlalchemy import select as sa_select
        result = await db.execute(sa_select(Thread).where(Thread.id == thread_id))
        thread = result.scalar_one_or_none()
        if thread and thread.name == 'New Chat':
            await auto_name_thread(db, thread, prompt)

    history = await get_message_history(db, user.id, limit=20, thread_id=thread_id)
    history_messages = [
        {'role': message.role, 'content': message.content}
        for message in history
        if message.role in {'system', 'user', 'assistant'}
    ]

    if not history_messages or history_messages[-1]['role'] != 'user':
        history_messages.append({'role': 'user', 'content': prompt})

    if history_messages and history_messages[-1]['role'] == 'user':
        user_text = history_messages[-1]['content']
        if attachment_context:
            user_text = f"{user_text}\n\n{attachment_context}"

        if attachment_image_inputs:
            history_messages[-1]['content'] = [
                {'type': 'text', 'text': user_text},
                *attachment_image_inputs,
            ]
        else:
            history_messages[-1]['content'] = user_text

    messages = build_memory_window(history_messages, max_previous_conversations=5)

    assistant_parts: list[str] = []

    try:
        async for token in stream_chain_tokens(messages, user_email=user.email):
            assistant_parts.append(token)
            yield _sse_data({'type': 'token', 'content': token})

        full_response = ''.join(assistant_parts).strip()
        if full_response:
            response_for_storage = full_response
            if attachment_label:
                response_for_storage = f"{response_for_storage}\n\n[Used files: {attachment_label}]"
            await save_message(db, user.id, 'assistant', response_for_storage, thread_id)

        yield _sse_data({'type': 'done'})
    except Exception as exc:  # noqa: BLE001
        yield _sse_error(str(exc))


def _sse_data(payload: dict[str, str]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _sse_error(message: str) -> str:
    return _sse_data({'type': 'error', 'message': message})


async def _trigger_n8n_sidecar(*, db: AsyncSession, user: User, prompt: str, thread_id: str | None) -> None:
    """Trigger n8n webhook for each incoming user message.

    This should never interrupt chat generation if n8n is down or misconfigured.
    """
    from app.services.n8n_service import N8nWebhookError, trigger_webhook

    payload = {
        'user_id': user.id,
        'user_name': user.name or user.email,
        'conversation_id': thread_id or '',
        'message': prompt,
    }

    try:
        result = await trigger_webhook(payload)
        await _save_n8n_audit_event(
            db=db,
            user_id=user.id,
            thread_id=thread_id,
            conversation_id=payload['conversation_id'],
            message=prompt,
            status='success',
            http_status=int(result.get('http_status')) if isinstance(result, dict) and result.get('http_status') else 200,
            response_body=json.dumps(result) if isinstance(result, (dict, list)) else str(result),
            error_message=None,
        )
    except N8nWebhookError as exc:
        await _save_n8n_audit_event(
            db=db,
            user_id=user.id,
            thread_id=thread_id,
            conversation_id=payload['conversation_id'],
            message=prompt,
            status='failed',
            http_status=None,
            response_body=None,
            error_message=str(exc),
        )
        logger.warning('n8n sidecar trigger skipped: %s', exc)


async def _save_n8n_audit_event(
    *,
    db: AsyncSession,
    user_id: str,
    thread_id: str | None,
    conversation_id: str,
    message: str,
    status: str,
    http_status: int | None,
    response_body: str | None,
    error_message: str | None,
) -> None:
    event = N8nWebhookEvent(
        user_id=user_id,
        thread_id=thread_id,
        conversation_id=conversation_id,
        message=message,
        status=status,
        http_status=http_status,
        response_body=response_body,
        error_message=error_message,
    )
    db.add(event)
    await db.commit()
