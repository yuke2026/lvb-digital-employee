"""Topic CRUD router + topic_sources M2M"""
from uuid import UUID
from datetime import datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["主题"])


# ===== Inline schemas =====

class SourceAttachRequest(BaseModel):
    source_id: UUID


class TopicBase(BaseModel):
    name: str = Field(..., max_length=100)
    category: str = Field(..., max_length=50)
    keywords: list[str] = Field(...)
    exclude_keywords: list[str] = []
    push_cycle: str = "daily"
    push_time: time = time(8, 30)


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[list[str]] = None
    exclude_keywords: Optional[list[str]] = None
    push_cycle: Optional[str] = None
    push_time: Optional[time] = None
    is_active: Optional[bool] = None


class TopicResponse(TopicBase):
    id: UUID
    org_id: UUID
    user_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SourceResponse(BaseModel):
    id: UUID
    name: str
    source_type: str
    url: str

    model_config = {"from_attributes": True}


# ===== Helpers =====

async def _row_to_topic(row) -> TopicResponse:
    return TopicResponse(
        id=row.id,
        org_id=row.org_id,
        user_id=row.user_id,
        name=row.name,
        category=row.category,
        keywords=row.keywords if isinstance(row.keywords, list) else [],
        exclude_keywords=row.exclude_keywords if isinstance(row.exclude_keywords, list) else [],
        push_cycle=row.push_cycle,
        push_time=row.push_time,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ===== Endpoints =====

@router.get("", response_model=list[TopicResponse])
async def list_topics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all topics for the current user's organization."""
    result = await db.execute(
        text("""
            SELECT id, org_id, user_id, name, category, keywords, exclude_keywords,
                   push_cycle, push_time, is_active, created_at, updated_at
            FROM topics
            WHERE org_id = :org_id
            ORDER BY created_at DESC
        """),
        {"org_id": str(current_user.org_id)},
    )
    rows = result.fetchall()
    return [await _row_to_topic(row) for row in rows]


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    topic_in: TopicCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new topic for the current user's organization."""
    now = datetime.utcnow()
    result = await db.execute(
        text("""
            INSERT INTO topics (org_id, user_id, name, category, keywords, exclude_keywords,
                                push_cycle, push_time, is_active, created_at, updated_at)
            VALUES (:org_id, :user_id, :name, :category, :keywords, :exclude_keywords,
                    :push_cycle, :push_time, true, :created_at, :updated_at)
            RETURNING id, org_id, user_id, name, category, keywords, exclude_keywords,
                      push_cycle, push_time, is_active, created_at, updated_at
        """),
        {
            "org_id": str(current_user.org_id),
            "user_id": str(current_user.id),
            "name": topic_in.name,
            "category": topic_in.category,
            "keywords": topic_in.keywords,
            "exclude_keywords": topic_in.exclude_keywords,
            "push_cycle": topic_in.push_cycle,
            "push_time": topic_in.push_time,
            "created_at": now,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    return await _row_to_topic(row)


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single topic by ID."""
    result = await db.execute(
        text("""
            SELECT id, org_id, user_id, name, category, keywords, exclude_keywords,
                   push_cycle, push_time, is_active, created_at, updated_at
            FROM topics
            WHERE id = :topic_id AND org_id = :org_id
        """),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return await _row_to_topic(row)


@router.put("/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: UUID,
    topic_in: TopicUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a topic."""
    # Build dynamic SET clause from provided fields
    fields = {}
    set_clauses = []
    if topic_in.name is not None:
        set_clauses.append("name = :name")
        fields["name"] = topic_in.name
    if topic_in.category is not None:
        set_clauses.append("category = :category")
        fields["category"] = topic_in.category
    if topic_in.keywords is not None:
        set_clauses.append("keywords = :keywords")
        fields["keywords"] = topic_in.keywords
    if topic_in.exclude_keywords is not None:
        set_clauses.append("exclude_keywords = :exclude_keywords")
        fields["exclude_keywords"] = topic_in.exclude_keywords
    if topic_in.push_cycle is not None:
        set_clauses.append("push_cycle = :push_cycle")
        fields["push_cycle"] = topic_in.push_cycle
    if topic_in.push_time is not None:
        set_clauses.append("push_time = :push_time")
        fields["push_time"] = topic_in.push_time
    if topic_in.is_active is not None:
        set_clauses.append("is_active = :is_active")
        fields["is_active"] = topic_in.is_active

    if not set_clauses:
        # No fields to update, just return current topic
        return await get_topic(topic_id, current_user, db)

    set_clauses.append("updated_at = :updated_at")
    fields["updated_at"] = datetime.utcnow()
    fields["topic_id"] = str(topic_id)
    fields["org_id"] = str(current_user.org_id)

    query = text(f"""
        UPDATE topics
        SET {', '.join(set_clauses)}
        WHERE id = :topic_id AND org_id = :org_id
        RETURNING id, org_id, user_id, name, category, keywords, exclude_keywords,
                  push_cycle, push_time, is_active, created_at, updated_at
    """)
    result = await db.execute(query, fields)
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return await _row_to_topic(row)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a topic and its source associations."""
    # Delete M2M associations first
    await db.execute(
        text("DELETE FROM topic_sources WHERE topic_id = :topic_id"),
        {"topic_id": str(topic_id)},
    )
    result = await db.execute(
        text("DELETE FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")


@router.post("/{topic_id}/sources", status_code=status.HTTP_201_CREATED)
async def attach_source(
    topic_id: UUID,
    req: SourceAttachRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a news source to a topic."""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    # Verify source belongs to org
    result = await db.execute(
        text("SELECT id FROM news_sources WHERE id = :source_id AND org_id = :org_id"),
        {"source_id": str(req.source_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    # Insert M2M (ignore if already exists)
    await db.execute(
        text("""
            INSERT INTO topic_sources (topic_id, source_id, created_at)
            VALUES (:topic_id, :source_id, :created_at)
            ON CONFLICT (topic_id, source_id) DO NOTHING
        """),
        {"topic_id": str(topic_id), "source_id": str(req.source_id), "created_at": datetime.utcnow()},
    )
    await db.commit()
    return {"message": "Source attached"}


@router.delete("/{topic_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_source(
    topic_id: UUID,
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detach a news source from a topic."""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    result = await db.execute(
        text("DELETE FROM topic_sources WHERE topic_id = :topic_id AND source_id = :source_id"),
        {"topic_id": str(topic_id), "source_id": str(source_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source association not found")
