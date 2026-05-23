from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.n8n_webhook_event import N8nWebhookEvent
from app.models.user import User
from app.services.n8n_service import N8nWebhookError, get_workflow_status, trigger_webhook

router = APIRouter(prefix='/n8n', tags=['n8n'])


class WebhookTriggerRequest(BaseModel):
    user_id: str = Field(min_length=1)
    user_name: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class WebhookTriggerResponse(BaseModel):
    success: bool
    result: dict[str, Any]


class WorkflowStatusResponse(BaseModel):
    success: bool
    result: dict[str, Any]


class N8nWebhookEventOut(BaseModel):
    id: str
    user_id: str
    thread_id: str | None
    conversation_id: str
    message: str
    status: str
    http_status: int | None
    response_body: str | None
    error_message: str | None
    created_at: datetime


@router.post('/trigger', response_model=WebhookTriggerResponse)
async def n8n_trigger(
    body: WebhookTriggerRequest,
    current_user: User = Depends(get_current_user),
) -> WebhookTriggerResponse:
    """Send a message payload to the configured N8N_WEBHOOK_URL and return the response."""
    del current_user
    payload = {
        'user_id': body.user_id,
        'user_name': body.user_name,
        'conversation_id': body.conversation_id,
        'message': body.message,
    }
    try:
        result = await trigger_webhook(payload)
        return WebhookTriggerResponse(success=True, result=result)
    except N8nWebhookError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/status/{run_id}', response_model=WorkflowStatusResponse)
async def n8n_status(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> WorkflowStatusResponse:
    """Query workflow run status via N8N_STATUS_WEBHOOK_URL."""
    del current_user
    try:
        result = await get_workflow_status(run_id)
        return WorkflowStatusResponse(success=True, result=result)
    except N8nWebhookError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/events/recent', response_model=list[N8nWebhookEventOut])
async def n8n_recent_events(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[N8nWebhookEventOut]:
    del current_user
    capped_limit = max(1, min(limit, 100))
    stmt = select(N8nWebhookEvent).order_by(N8nWebhookEvent.created_at.desc()).limit(capped_limit)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    return [
        N8nWebhookEventOut(
            id=row.id,
            user_id=row.user_id,
            thread_id=row.thread_id,
            conversation_id=row.conversation_id,
            message=row.message,
            status=row.status,
            http_status=row.http_status,
            response_body=row.response_body,
            error_message=row.error_message,
            created_at=row.created_at,
        )
        for row in rows
    ]
