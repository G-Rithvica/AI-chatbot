from __future__ import annotations

import httpx

from app.core.config import get_settings


class N8nWebhookError(RuntimeError):
    """Raised when the n8n webhook call fails."""


def _build_headers() -> dict[str, str]:
    settings = get_settings()
    headers: dict[str, str] = {'Content-Type': 'application/json'}
    if settings.n8n_api_key and settings.n8n_api_key.strip():
        headers['X-N8N-API-KEY'] = settings.n8n_api_key.strip()
    return headers


async def trigger_webhook(payload: dict) -> dict:
    """POST payload to N8N_WEBHOOK_URL and return the JSON response.

    Raises N8nWebhookError if the URL is not configured or the request fails.
    """
    settings = get_settings()
    url = (settings.n8n_webhook_url or '').strip()
    if not url:
        raise N8nWebhookError(
            'N8N_WEBHOOK_URL is not configured. Set it in your .env file.'
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=_build_headers())
            response.raise_for_status()
            # n8n webhooks may return empty body on success
            if response.content:
                return response.json()
            return {'status': 'ok', 'http_status': response.status_code}
    except httpx.HTTPStatusError as exc:
        raise N8nWebhookError(
            f'n8n webhook returned {exc.response.status_code}: {exc.response.text}'
        ) from exc
    except httpx.RequestError as exc:
        raise N8nWebhookError(f'Failed to reach n8n webhook: {exc}') from exc


async def get_workflow_status(run_id: str) -> dict:
    """POST to N8N_STATUS_WEBHOOK_URL to query a workflow run status.

    Raises N8nWebhookError if the status URL is not configured or the request fails.
    """
    settings = get_settings()
    url = (settings.n8n_status_webhook_url or '').strip()
    if not url:
        raise N8nWebhookError(
            'N8N_STATUS_WEBHOOK_URL is not configured. Set it in your .env file.'
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url, json={'run_id': run_id}, headers=_build_headers()
            )
            response.raise_for_status()
            if response.content:
                return response.json()
            return {'status': 'ok', 'run_id': run_id}
    except httpx.HTTPStatusError as exc:
        raise N8nWebhookError(
            f'n8n status webhook returned {exc.response.status_code}: {exc.response.text}'
        ) from exc
    except httpx.RequestError as exc:
        raise N8nWebhookError(f'Failed to reach n8n status webhook: {exc}') from exc
