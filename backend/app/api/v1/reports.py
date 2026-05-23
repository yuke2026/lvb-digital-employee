"""Reports CRUD router"""
from uuid import UUID
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["报告"])


# ===== Inline schemas =====

class ReportCreateRequest(BaseModel):
    topic_id: UUID
    report_type: str = Field(..., max_length=20)


class ReportResponse(BaseModel):
    id: UUID
    topic_id: UUID
    report_type: str
    title: str
    summary: Optional[str] = None
    content: Optional[dict] = None
    swot: Optional[dict] = None
    risk_level: Optional[str] = None
    risk_items: Optional[dict] = None
    opportunities: Optional[dict] = None
    push_time: Optional[datetime] = None
    status: str
    feishu_doc_token: Optional[str] = None
    feishu_msg_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ===== Helpers =====

async def _row_to_report(row) -> ReportResponse:
    return ReportResponse(
        id=row.id,
        topic_id=row.topic_id,
        report_type=row.report_type,
        title=row.title,
        summary=row.summary,
        content=row.content,
        swot=row.swot,
        risk_level=row.risk_level,
        risk_items=row.risk_items,
        opportunities=row.opportunities,
        push_time=row.push_time,
        status=row.status,
        feishu_doc_token=row.feishu_doc_token,
        feishu_msg_id=row.feishu_msg_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ===== Endpoints =====

@router.get("", response_model=list[ReportResponse])
async def list_reports(
    topic_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List reports for the current user's organization, optionally filtered by topic_id."""
    params = {"org_id": str(current_user.org_id)}
    where_clauses = ["t.org_id = :org_id"]

    if topic_id is not None:
        where_clauses.append("r.topic_id = :topic_id")
        params["topic_id"] = str(topic_id)

    query = text(f"""
        SELECT r.id, r.topic_id, r.report_type, r.title, r.summary,
               r.content, r.swot, r.risk_level, r.risk_items, r.opportunities,
               r.push_time, r.status, r.feishu_doc_token, r.feishu_msg_id,
               r.created_at, r.updated_at
        FROM reports r
        JOIN topics t ON r.topic_id = t.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY r.created_at DESC
    """)
    result = await db.execute(query, params)
    rows = result.fetchall()
    return [await _row_to_report(row) for row in rows]


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    report_in: ReportCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new report for the given topic by calling report_generator.generate_report."""
    # Verify topic belongs to org
    topic_result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(report_in.topic_id), "org_id": str(current_user.org_id)},
    )
    if not topic_result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    # Call the report generator service
    from app.services.report_generator import generate_report
    report_data = await generate_report(
        topic_id=report_in.topic_id,
        report_type=report_in.report_type,
        org_id=current_user.org_id,
        user_id=current_user.id,
    )

    now = datetime.utcnow()
    result = await db.execute(
        text("""
            INSERT INTO reports (topic_id, report_type, title, summary, content, swot,
                                 risk_level, risk_items, opportunities, push_time,
                                 status, feishu_doc_token, feishu_msg_id,
                                 created_at, updated_at)
            VALUES (:topic_id, :report_type, :title, :summary, :content, :swot,
                    :risk_level, :risk_items, :opportunities, :push_time,
                    :status, :feishu_doc_token, :feishu_msg_id,
                    :created_at, :updated_at)
            RETURNING id, topic_id, report_type, title, summary, content, swot,
                      risk_level, risk_items, opportunities, push_time,
                      status, feishu_doc_token, feishu_msg_id,
                      created_at, updated_at
        """),
        {
            "topic_id": str(report_in.topic_id),
            "report_type": report_in.report_type,
            "title": report_data.get("title", ""),
            "summary": report_data.get("summary"),
            "content": report_data.get("content"),
            "swot": report_data.get("swot"),
            "risk_level": report_data.get("risk_level"),
            "risk_items": report_data.get("risk_items"),
            "opportunities": report_data.get("opportunities"),
            "push_time": report_data.get("push_time"),
            "status": report_data.get("status", "draft"),
            "feishu_doc_token": report_data.get("feishu_doc_token"),
            "feishu_msg_id": report_data.get("feishu_msg_id"),
            "created_at": now,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    await db.commit()
    return await _row_to_report(row)


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single report by ID."""
    result = await db.execute(
        text("""
            SELECT r.id, r.topic_id, r.report_type, r.title, r.summary,
                   r.content, r.swot, r.risk_level, r.risk_items, r.opportunities,
                   r.push_time, r.status, r.feishu_doc_token, r.feishu_msg_id,
                   r.created_at, r.updated_at
            FROM reports r
            JOIN topics t ON r.topic_id = t.id
            WHERE r.id = :report_id AND t.org_id = :org_id
        """),
        {"report_id": str(report_id), "org_id": str(current_user.org_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return await _row_to_report(row)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report."""
    result = await db.execute(
        text("""
            DELETE FROM reports
            WHERE id = :report_id
              AND topic_id IN (SELECT id FROM topics WHERE org_id = :org_id)
        """),
        {"report_id": str(report_id), "org_id": str(current_user.org_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
