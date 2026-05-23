"""推送配置 API - 管理主题的飞书推送设置"""
from uuid import UUID
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["推送配置"])


class PushConfigResponse(BaseModel):
    id: UUID
    topic_id: UUID
    feishu_chat_id: Optional[str] = None
    feishu_push_enabled: bool = False
    email_push_enabled: bool = False
    email_recipients: list[str] = []
    webhook_url: Optional[str] = None


class PushConfigUpdate(BaseModel):
    feishu_chat_id: Optional[str] = None
    feishu_push_enabled: bool = False
    email_push_enabled: bool = False
    email_recipients: list[str] = []
    webhook_url: Optional[str] = None


class PushConfigCreate(BaseModel):
    topic_id: UUID
    feishu_chat_id: Optional[str] = None
    feishu_push_enabled: bool = False
    email_push_enabled: bool = False
    email_recipients: list[str] = []
    webhook_url: Optional[str] = None


@router.get("/topic/{topic_id}", response_model=PushConfigResponse)
async def get_push_config(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定主题的推送配置"""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    result = await db.execute(
        text("""
            SELECT id, topic_id, feishu_chat_id, feishu_push_enabled,
                   email_push_enabled, email_recipients, webhook_url
            FROM topic_push_configs
            WHERE topic_id = :topic_id
        """),
        {"topic_id": str(topic_id)},
    )
    row = result.fetchone()
    if not row:
        # Return default (not configured)
        return PushConfigResponse(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            topic_id=topic_id,
            feishu_chat_id=None,
            feishu_push_enabled=False,
            email_push_enabled=False,
            email_recipients=[],
            webhook_url=None,
        )
    return PushConfigResponse(
        id=row.id,
        topic_id=row.topic_id,
        feishu_chat_id=row.feishu_chat_id,
        feishu_push_enabled=row.feishu_push_enabled,
        email_push_enabled=row.email_push_enabled,
        email_recipients=row.email_recipients or [],
        webhook_url=row.webhook_url,
    )


@router.put("/topic/{topic_id}", response_model=PushConfigResponse)
async def upsert_push_config(
    topic_id: UUID,
    cfg: PushConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建或更新主题的推送配置（upsert）"""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    now = datetime.utcnow()
    result = await db.execute(
        text("""
            INSERT INTO topic_push_configs
                (topic_id, feishu_chat_id, feishu_push_enabled, email_push_enabled,
                 email_recipients, webhook_url, updated_at)
            VALUES (:topic_id, :feishu_chat_id, :feishu_push_enabled, :email_push_enabled,
                    :email_recipients, :webhook_url, :updated_at)
            ON CONFLICT (topic_id) DO UPDATE SET
                feishu_chat_id = EXCLUDED.feishu_chat_id,
                feishu_push_enabled = EXCLUDED.feishu_push_enabled,
                email_push_enabled = EXCLUDED.email_push_enabled,
                email_recipients = EXCLUDED.email_recipients,
                webhook_url = EXCLUDED.webhook_url,
                updated_at = EXCLUDED.updated_at
            RETURNING id, topic_id, feishu_chat_id, feishu_push_enabled,
                       email_push_enabled, email_recipients, webhook_url
        """),
        {
            "topic_id": str(topic_id),
            "feishu_chat_id": cfg.feishu_chat_id,
            "feishu_push_enabled": cfg.feishu_push_enabled,
            "email_push_enabled": cfg.email_push_enabled,
            "email_recipients": cfg.email_recipients,
            "webhook_url": cfg.webhook_url,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    await db.commit()
    return PushConfigResponse(
        id=row.id,
        topic_id=row.topic_id,
        feishu_chat_id=row.feishu_chat_id,
        feishu_push_enabled=row.feishu_push_enabled,
        email_push_enabled=row.email_push_enabled,
        email_recipients=row.email_recipients or [],
        webhook_url=row.webhook_url,
    )


@router.delete("/topic/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_push_config(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除主题的推送配置"""
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    await db.execute(
        text("DELETE FROM topic_push_configs WHERE topic_id = :topic_id"),
        {"topic_id": str(topic_id)},
    )
    await db.commit()
