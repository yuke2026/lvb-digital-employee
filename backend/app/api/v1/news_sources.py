"""News sources CRUD router (raw SQL, no SQLAlchemy model yet)."""
import json
from datetime import datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.source import (
    NewsSourceCreate,
    NewsSourceResponse,
    NewsSourceUpdate,
)

router = APIRouter(prefix="/news-sources", tags=["news-sources"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_source(row: tuple) -> NewsSourceResponse:
    """Convert a raw DB row (by-index) to NewsSourceResponse."""
    (
        id_,
        name,
        source_type,
        url,
        update_freq,
        is_active,
        last_fetch_at,
        last_fetch_status,
        config,
        created_at,
        org_id,
    ) = row
    return NewsSourceResponse(
        id=id_,
        name=name,
        source_type=source_type,
        url=url,
        update_freq=update_freq or "1h",
        is_active=is_active,
        last_fetch_at=last_fetch_at,
        last_fetch_status=last_fetch_status,
        config=config if isinstance(config, dict) else json.loads(config) if config else {},
        created_at=created_at,
    )


# ------------------------------------------------------------------
# GET /  (list, filtered by org_id)
# ------------------------------------------------------------------


@router.get("", response_model=list[NewsSourceResponse])
async def list_news_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all news sources belonging to the current user's org."""
    query = text(
        """
        SELECT id, name, source_type, url, update_freq, is_active,
               last_fetch_at, last_fetch_status, config, created_at, org_id
        FROM news_sources
        WHERE org_id = :org_id
        ORDER BY created_at DESC
        """
    )
    result = await db.execute(query, {"org_id": str(current_user.org_id)})
    rows = result.fetchall()
    return [_row_to_source(row) for row in rows]


# ------------------------------------------------------------------
# POST /  (create)
# ------------------------------------------------------------------


@router.post("", response_model=NewsSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_news_source(
    source_in: NewsSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new news source for the current user's org."""
    if current_user.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前用户没有所属组织，无法创建新闻源",
        )

    query = text(
        """
        INSERT INTO news_sources (name, source_type, url, update_freq, config, org_id)
        VALUES (:name, :source_type, :url, :update_freq, :config::jsonb, :org_id)
        RETURNING id, name, source_type, url, update_freq, is_active,
                  last_fetch_at, last_fetch_status, config, created_at, org_id
        """
    )
    params = {
        "name": source_in.name,
        "source_type": source_in.source_type,
        "url": source_in.url,
        "update_freq": source_in.update_freq,
        "config": json.dumps(source_in.config or {}),
        "org_id": str(current_user.org_id),
    }
    result = await db.execute(query, params)
    row = result.fetchone()
    await db.commit()
    return _row_to_source(row)


# ------------------------------------------------------------------
# GET /{id}  (get one, filtered by org_id)
# ------------------------------------------------------------------


@router.get("/{source_id}", response_model=NewsSourceResponse)
async def get_news_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single news source by ID (must belong to current user's org)."""
    query = text(
        """
        SELECT id, name, source_type, url, update_freq, is_active,
               last_fetch_at, last_fetch_status, config, created_at, org_id
        FROM news_sources
        WHERE id = :id AND org_id = :org_id
        """
    )
    result = await db.execute(
        query, {"id": str(source_id), "org_id": str(current_user.org_id)}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="新闻源不存在或无权访问",
        )
    return _row_to_source(row)


# ------------------------------------------------------------------
# PUT /{id}  (update, filtered by org_id)
# ------------------------------------------------------------------


@router.put("/{source_id}", response_model=NewsSourceResponse)
async def update_news_source(
    source_id: UUID,
    source_in: NewsSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a news source (must belong to current user's org)."""
    # First verify ownership
    check_query = text(
        "SELECT 1 FROM news_sources WHERE id = :id AND org_id = :org_id"
    )
    check_result = await db.execute(
        check_query, {"id": str(source_id), "org_id": str(current_user.org_id)}
    )
    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="新闻源不存在或无权访问",
        )

    # Build dynamic SET clause from provided fields
    updates = {}
    set_clauses = []

    if source_in.name is not None:
        set_clauses.append("name = :name")
        updates["name"] = source_in.name
    if source_in.source_type is not None:
        set_clauses.append("source_type = :source_type")
        updates["source_type"] = source_in.source_type
    if source_in.url is not None:
        set_clauses.append("url = :url")
        updates["url"] = source_in.url
    if source_in.update_freq is not None:
        set_clauses.append("update_freq = :update_freq")
        updates["update_freq"] = source_in.update_freq
    if source_in.is_active is not None:
        set_clauses.append("is_active = :is_active")
        updates["is_active"] = source_in.is_active
    if source_in.config is not None:
        set_clauses.append("config = :config::jsonb")
        updates["config"] = json.dumps(source_in.config)

    if not set_clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有提供任何更新字段",
        )

    query = text(
        f"""
        UPDATE news_sources
        SET {", ".join(set_clauses)}
        WHERE id = :id AND org_id = :org_id
        RETURNING id, name, source_type, url, update_freq, is_active,
                  last_fetch_at, last_fetch_status, config, created_at, org_id
        """
    )
    updates["id"] = str(source_id)
    updates["org_id"] = str(current_user.org_id)

    result = await db.execute(query, updates)
    row = result.fetchone()
    await db.commit()
    return _row_to_source(row)


# ------------------------------------------------------------------
# DELETE /{id}  (delete, filtered by org_id)
# ------------------------------------------------------------------


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a news source (must belong to current user's org)."""
    query = text(
        """
        DELETE FROM news_sources
        WHERE id = :id AND org_id = :org_id
        RETURNING id
        """
    )
    result = await db.execute(
        query, {"id": str(source_id), "org_id": str(current_user.org_id)}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="新闻源不存在或无权访问",
        )
    await db.commit()


# ------------------------------------------------------------------
# POST /{id}/test  (test connection)
# ------------------------------------------------------------------


@router.post("/{source_id}/test")
async def test_news_source_connection(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test connectivity to a news source URL (HEAD request)."""
    # Verify ownership
    query = text(
        """
        SELECT url, source_type, config
        FROM news_sources
        WHERE id = :id AND org_id = :org_id
        """
    )
    result = await db.execute(
        query, {"id": str(source_id), "org_id": str(current_user.org_id)}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="新闻源不存在或无权访问",
        )

    url, source_type, config = row
    config = config if isinstance(config, dict) else json.loads(config) if config else {}

    # Basic HEAD request test (works for RSS/API/crawl)
    timeout = config.get("timeout", 10)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(url)
            reachable = response.status_code < 500
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"连接超时（{timeout}秒）",
        )
    except httpx.RequestError:
        # Fallback: try GET if HEAD is not supported
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                reachable = response.status_code < 500
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法连接到目标地址: {str(e)}",
            )

    return {
        "source_id": str(source_id),
        "source_type": source_type,
        "url": url,
        "reachable": reachable,
        "status_code": response.status_code if "response" in dir() else None,
        "message": "连接成功" if reachable else "服务器返回错误",
    }
