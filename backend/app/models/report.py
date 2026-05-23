"""Report model (SQLAlchemy)"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Report(Base):
    """Report model for storing generated analysis reports"""
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    swot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    risk_items: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    opportunities: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    push_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    feishu_doc_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    feishu_msg_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
