"""调度管理 API - 管理定时采集和报告任务"""
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
from app.services.scheduler import (
    schedule_collect,
    schedule_report,
    remove_topic_jobs,
    list_scheduled_jobs,
    get_scheduler,
    start_scheduler,
)

router = APIRouter(tags=["调度管理"])


# ===== Schemas =====

class ScheduleCollectRequest(BaseModel):
    topic_id: UUID
    cron_expr: str = Field(default="0 */6 * * *", description="Cron表达式（分 时 日 月 周）")


class ScheduleReportRequest(BaseModel):
    topic_id: UUID
    report_type: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)


class RemoveTopicScheduleRequest(BaseModel):
    topic_id: UUID


class JobInfo(BaseModel):
    id: str
    name: str
    next_run_time: Optional[str]
    trigger: str


class JobListResponse(BaseModel):
    jobs: list[JobInfo]
    scheduler_running: bool


class ScheduleResponse(BaseModel):
    message: str
    job_id: str


# ===== Endpoints =====

@router.post("/collect", response_model=ScheduleResponse)
async def schedule_collection(
    req: ScheduleCollectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为指定主题设置定时采集任务"""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(req.topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    # Ensure scheduler is running
    start_scheduler()

    schedule_collect(
        topic_id=req.topic_id,
        org_id=current_user.org_id,
        cron_expr=req.cron_expr,
    )

    # 持久化到数据库
    from app.services.scheduler import _collect_job_name
    job_id = _collect_job_name(req.topic_id)
    now = datetime.utcnow()
    await db.execute(
        text("""
            INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, next_run_at, created_at, updated_at)
            VALUES (:topic_id, 'collect', :cron_expr, 0, 0, TRUE, NULL, :now, :now)
            ON CONFLICT (topic_id) WHERE job_type = 'collect'
            DO UPDATE SET cron_expr = :cron_expr, is_active = TRUE, updated_at = :now
        """),
        {"topic_id": str(req.topic_id), "cron_expr": req.cron_expr, "now": now}
    )
    await db.commit()
    return ScheduleResponse(message="采集任务已设置", job_id=job_id)


@router.post("/report", response_model=ScheduleResponse)
async def schedule_report_endpoint(
    req: ScheduleReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为指定主题设置定时报告生成任务"""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(req.topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    start_scheduler()

    schedule_report(
        topic_id=req.topic_id,
        org_id=current_user.org_id,
        user_id=current_user.id,
        report_type=req.report_type,
        hour=req.hour,
        minute=req.minute,
    )

    # 持久化到数据库
    from app.services.scheduler import _report_job_name
    job_id = _report_job_name(req.topic_id, req.report_type)
    now = datetime.utcnow()
    await db.execute(
        text("""
            INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, next_run_at, created_at, updated_at)
            VALUES (:topic_id, :job_type, NULL, :hour, :minute, TRUE, NULL, :now, :now)
            ON CONFLICT (topic_id) WHERE job_type = :job_type
            DO UPDATE SET hour = :hour, minute = :minute, is_active = TRUE, updated_at = :now
        """),
        {"topic_id": str(req.topic_id), "job_type": f"report_{req.report_type}", "hour": req.hour, "minute": req.minute, "now": now}
    )
    await db.commit()
    return ScheduleResponse(
        message=f"{req.report_type}报告任务已设置",
        job_id=job_id,
    )


@router.delete("/topic/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_schedule(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """移除指定主题的所有定时任务"""
    # Verify topic belongs to org
    result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(current_user.org_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    remove_topic_jobs(topic_id)

    # 从数据库删除
    await db.execute(
        text("DELETE FROM scheduled_jobs WHERE topic_id = :topic_id"),
        {"topic_id": str(topic_id)}
    )
    await db.commit()


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(current_user: User = Depends(get_current_user)):
    """列出所有定时任务"""
    sched = get_scheduler()
    jobs = list_scheduled_jobs()
    return JobListResponse(
        jobs=[JobInfo(**j) for j in jobs],
        scheduler_running=sched.running if sched else False,
    )
