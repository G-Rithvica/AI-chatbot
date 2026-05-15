from datetime import datetime

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    thread_id: str
    attachment_ids: list[str] | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class GeneratedImageOut(BaseModel):
    id: str
    thread_id: str
    prompt: str
    revised_prompt: str | None
    mime_type: str
    image_base64: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    messages: list[ChatMessageOut]
    generated_images: list[GeneratedImageOut] = []
