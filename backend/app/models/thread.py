import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Thread(Base):
    __tablename__ = 'threads'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default='New Chat')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship('User', back_populates='threads')
    messages = relationship('Message', back_populates='thread', cascade='all, delete-orphan', order_by='Message.created_at')
    attachments = relationship('Attachment', back_populates='thread', cascade='all, delete-orphan', order_by='Attachment.created_at')
    generated_images = relationship(
        'GeneratedImage',
        back_populates='thread',
        cascade='all, delete-orphan',
        order_by='GeneratedImage.created_at',
    )
