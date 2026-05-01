from openai import AsyncOpenAI, OpenAI

from app.core.config import get_settings

settings = get_settings()

_sync_client: OpenAI | None = None
_async_client: AsyncOpenAI | None = None


def get_openai_client() -> OpenAI:
	global _sync_client
	if _sync_client is None:
		_sync_client = OpenAI(
			api_key=settings.litellm_api_key,
			base_url=settings.litellm_proxy_url,
		)
	return _sync_client


def get_async_openai_client() -> AsyncOpenAI:
	global _async_client
	if _async_client is None:
		_async_client = AsyncOpenAI(
			api_key=settings.litellm_api_key,
			base_url=settings.litellm_proxy_url,
		)
	return _async_client
