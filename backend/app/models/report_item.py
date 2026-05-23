"""Report item model (SQLAlchemy)"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ReportItem(Base):
    """Report item model for storing report article entries"""
    __tablename__ = "report_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"), nullable=False, index=True)
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("raw_articles.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_key_event: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
