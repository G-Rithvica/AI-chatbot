from datetime import datetime

from pydantic import BaseModel, Field


class ThreadOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class ThreadListOut(BaseModel):
    threads: list[ThreadOut]


class ThreadCreateIn(BaseModel):
    name: str = Field(default='New Chat', max_length=255)


class ThreadRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
