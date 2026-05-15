from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: str
    file_name: str
    mime_type: str
    size_bytes: int
    kind: str
    url: str
    created_at: datetime


class AttachmentListOut(BaseModel):
    attachments: list[AttachmentOut]
