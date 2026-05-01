from datetime import datetime

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    thread_id: str


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    messages: list[ChatMessageOut]
