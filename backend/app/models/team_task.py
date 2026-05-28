"""产研团队任务模型"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TeamTask(Base):
    """产研团队任务"""
    __tablename__ = "team_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    assignee: Mapped[str] = mapped_column(String(50), nullable=False)  # PM, RD, QA, UI
    status: Mapped[str] = mapped_column(String(20), default="backlog")  # backlog, design, dev, review, qa, done
    priority: Mapped[str] = mapped_column(String(5), default="P2")  # P0, P1, P2
    created_by: Mapped[str] = mapped_column(String(50), default="user")
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=datetime.utcnow)


class TaskLog(Base):
    """任务操作日志"""
    __tablename__ = "task_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # created, assigned, moved, completed
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    actor: Mapped[str] = mapped_column(String(50), default="system")  # user, PM, RD, QA, UI, system
    message: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
