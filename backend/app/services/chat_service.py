import json
from collections.abc import AsyncGenerator

from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_async_openai_client
from app.core.config import get_settings
from app.models.message import Message
from app.models.user import User

settings = get_settings()


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
) -> AsyncGenerator[str, None]:
    if not settings.llm_model:
        yield _sse_error('LLM_MODEL is not configured.')
        return

    await save_message(db, user.id, 'user', prompt, thread_id)

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
    messages = [
        {'role': message.role, 'content': message.content}
        for message in history
        if message.role in {'system', 'user', 'assistant'}
    ]

    if not messages or messages[-1]['role'] != 'user':
        messages.append({'role': 'user', 'content': prompt})

    assistant_parts: list[str] = []

    try:
        client = get_async_openai_client()
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            stream=True,
            user=user.email,
            extra_body={
                'metadata': {
                    'application': settings.app_name,
                    'environment': settings.environment,
                }
            },
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if not delta:
                continue
            assistant_parts.append(delta)
            yield _sse_data({'type': 'token', 'content': delta})

        full_response = ''.join(assistant_parts).strip()
        if full_response:
            await save_message(db, user.id, 'assistant', full_response, thread_id)

        yield _sse_data({'type': 'done'})
    except OpenAIError as exc:
        yield _sse_error(str(exc))
    except Exception as exc:  # noqa: BLE001
        yield _sse_error(str(exc))


def _sse_data(payload: dict[str, str]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _sse_error(message: str) -> str:
    return _sse_data({'type': 'error', 'message': message})
