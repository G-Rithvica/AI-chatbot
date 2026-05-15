import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GeneratedImage(Base):
    __tablename__ = 'generated_images'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey('threads.id', ondelete='CASCADE'), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    revised_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default='image/png')
    image_base64: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user = relationship('User', back_populates='generated_images')
    thread = relationship('Thread', back_populates='generated_images')
