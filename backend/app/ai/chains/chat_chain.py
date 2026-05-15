from collections.abc import AsyncGenerator
import logging
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

settings = get_settings()

_SYSTEM_PROMPT = (
    'You are an accurate, concise AI assistant for Amzur employees. '
    'Use provided conversation context and answer clearly. '
    'If the user message includes attached-file metadata or extracted file content, treat that as trusted input supplied by the application. '
    'Do not say you cannot access local files when attachment excerpts are provided; summarize or answer from the provided excerpt. '
    'When the user asks for a specific identifier such as Demo, Epic, or User, answer for that exact identifier only and do not blend details from similarly named items unless the user asks for comparison. '
    'For attachment-specific questions, ground the answer only in the attached-file context provided in the latest user message; if exact requested section is unavailable, state that explicitly and do not guess. '
    'When the user asks to generate, create, or draw an image, respond with: "Sure! Generating your image now..." — the application will automatically handle image generation. Do NOT say you cannot generate images.'
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ('system', _SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name='conversation'),
    ]
)

_chat_model: ChatOpenAI | None = None
_chat_model_non_streaming: ChatOpenAI | None = None

logger = logging.getLogger(__name__)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                maybe_text = item.get('text')
                if isinstance(maybe_text, str):
                    parts.append(maybe_text)
        return ''.join(parts)
    return ''


def _to_langchain_messages(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for item in messages:
        role = item.get('role')
        content = item.get('content', '')
        if role == 'user':
            converted.append(HumanMessage(content=content))
        elif role == 'assistant':
            converted.append(AIMessage(content=content))
        elif role == 'system':
            converted.append(SystemMessage(content=content))
    return converted


def get_chat_model() -> ChatOpenAI:
    global _chat_model
    if _chat_model is None:
        if not settings.llm_model:
            raise RuntimeError('LLM_MODEL is not configured.')
        _chat_model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_proxy_url,
            streaming=True,
            temperature=0,
        )
    return _chat_model


def get_chat_model_non_streaming() -> ChatOpenAI:
    global _chat_model_non_streaming
    if _chat_model_non_streaming is None:
        if not settings.llm_model:
            raise RuntimeError('LLM_MODEL is not configured.')
        _chat_model_non_streaming = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_proxy_url,
            streaming=False,
            temperature=0,
        )
    return _chat_model_non_streaming


async def stream_chain_tokens(
    conversation: list[dict[str, Any]],
    *,
    user_email: str,
) -> AsyncGenerator[str, None]:
    model = get_chat_model()
    langchain_messages = _to_langchain_messages(conversation)
    config = {
        'metadata': {
            'application': settings.app_name,
            'environment': settings.environment,
            'user': user_email,
        }
    }

    try:
        chain = _PROMPT | model
        async for chunk in chain.astream(
            {'conversation': langchain_messages},
            config=config,
        ):
            if isinstance(chunk, AIMessageChunk):
                token = _extract_text(chunk.content)
                if token:
                    yield token
        return
    except Exception as streaming_error:  # noqa: BLE001
        logger.warning('Streaming chat failed; falling back to non-streaming response: %s', streaming_error)

    # Resilience fallback for provider issues like mid-stream repeated chunks.
    fallback_model = get_chat_model_non_streaming()
    fallback_chain = _PROMPT | fallback_model
    response = await fallback_chain.ainvoke(
        {'conversation': langchain_messages},
        config=config,
    )
    text = _extract_text(getattr(response, 'content', ''))
    if text:
        yield text
