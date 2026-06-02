"""自动化配置 API — 管理每个主题的采集、报告、推送启停"""
import logging
from datetime import datetime
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/automation", tags=["自动化配置"])


# ===== Schemas =====

class TopicAutomationConfig(BaseModel):
    """单个主题的自动化配置"""
    topic_id: str
    topic_name: str
    category: str
    push_cycle: str = "daily"
    push_time: str = "08:30"
    collect_enabled: bool = False
    report_enabled: bool = False
    feishu_push_enabled: bool = False


class UpdateAutomationRequest(BaseModel):
    collect_enabled: Optional[bool] = None
    report_enabled: Optional[bool] = None
    feishu_push_enabled: Optional[bool] = None


# ===== Helpers =====

# 报告类型排序（用于层次调度）
_REPORT_HIERARCHY = ["daily", "weekly", "monthly", "quarterly", "yearly"]


def _get_higher_periods(base_cycle: str) -> list[str]:
    """从基准周期向上取所有周期（含基准）"""
    try:
        idx = _REPORT_HIERARCHY.index(base_cycle)
        return _REPORT_HIERARCHY[idx:]
    except ValueError:
        return [base_cycle]


# ===== Endpoints =====

@router.get("/configs", response_model=list[TopicAutomationConfig])
async def list_automation_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回当前用户组织下所有主题的自动化配置。
    采集和报告的 enabled 状态根据 scheduled_jobs 表实际记录判断。
    feishu_push 从 topic_push_configs 表读取。
    """
    org_id = str(current_user.org_id)

    # 1. 获取所有主题
    topics_result = await db.execute(
        text("""
            SELECT id, name, category, push_cycle, push_time
            FROM topics
            WHERE org_id = :org_id AND is_active = TRUE
            ORDER BY category, name
        """),
        {"org_id": org_id},
    )
    topics = topics_result.fetchall()
    if not topics:
        return []

    # 2. 获取该组织所有主题的调度任务
    topic_ids = [str(t.id) for t in topics]
    placeholders = ",".join(f"'{tid}'" for tid in topic_ids)
    jobs_result = await db.execute(
        text(f"""
            SELECT topic_id, job_type, is_active
            FROM scheduled_jobs
            WHERE topic_id IN ({placeholders}) AND is_active = TRUE
        """),
    )
    jobs = jobs_result.fetchall()

    # 构建每个 topic_id 的活跃 job_type 集合
    active_jobs: dict[str, set[str]] = {}
    for j in jobs:
        tid = j.topic_id
        if tid not in active_jobs:
            active_jobs[tid] = set()
        active_jobs[tid].add(j.job_type)

    # 3. 获取该组织所有主题的推送配置
    push_result = await db.execute(
        text(f"""
            SELECT topic_id, feishu_push_enabled
            FROM topic_push_configs
            WHERE topic_id IN ({placeholders})
        """),
    )
    push_configs: dict[str, bool] = {}
    for p in push_result.fetchall():
        push_configs[p.topic_id] = bool(p.feishu_push_enabled)

    # 4. 组装配置
    configs = []
    for t in topics:
        tid = str(t.id)
        topic_jobs = active_jobs.get(tid, set())

        # 判断采集是否启用：有 collect 类型的活跃 job
        collect_enabled = "collect" in topic_jobs

        # 判断报告是否启用：有至少一个 report_* 类型的活跃 job
        report_enabled = any(jt.startswith("report_") for jt in topic_jobs)

        feishu_enabled = push_configs.get(tid, False)

        # 解析推送时间
        push_time_str = t.push_time or "08:30"
        if isinstance(push_time_str, str) and len(push_time_str) > 5:
            push_time_str = push_time_str[:5]

        configs.append(TopicAutomationConfig(
            topic_id=tid,
            topic_name=t.name,
            category=t.category or "未分类",
            push_cycle=t.push_cycle or "daily",
            push_time=push_time_str,
            collect_enabled=collect_enabled,
            report_enabled=report_enabled,
            feishu_push_enabled=feishu_enabled,
        ))

    return configs


@router.put("/topics/{topic_id}/config", status_code=status.HTTP_200_OK)
async def update_automation_config(
    topic_id: UUID,
    req: UpdateAutomationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    更新单个主题的自动化配置。
    会自动启停对应的 APScheduler 实时任务并持久化到数据库。
    """
    org_id = current_user.org_id
    user_id = current_user.id

    # 1. 验证主题归属
    topic_result = await db.execute(
        text("SELECT id, name, push_cycle, push_time FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(topic_id), "org_id": str(org_id)},
    )
    topic_row = topic_result.fetchone()
    if not topic_row:
        raise HTTPException(status_code=404, detail="主题不存在或不属于当前组织")

    push_cycle = topic_row.push_cycle or "daily"
    push_time = topic_row.push_time or "08:30"
    if isinstance(push_time, str) and len(push_time) > 5:
        push_time = push_time[:5]

    # 解析时和分
    try:
        hour = int(push_time.split(":")[0])
        minute = int(push_time.split(":")[1])
    except (ValueError, IndexError):
        hour, minute = 8, 30

    start_scheduler()

    # 2. 处理采集启停
    if req.collect_enabled is not None:
        if req.collect_enabled:
            # 开启采集
            schedule_collect(
                topic_id=topic_id,
                org_id=org_id,
                cron_expr="0 */6 * * *",  # 默认每6小时
            )
            # 持久化（先删后插，避免 ON CONFLICT 不支持的问题）
            now = datetime.utcnow()
            await db.execute(
                text("DELETE FROM scheduled_jobs WHERE topic_id = :topic_id AND job_type = 'collect'"),
                {"topic_id": str(topic_id)},
            )
            await db.execute(
                text("""
                    INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, created_at, updated_at)
                    VALUES (:topic_id, 'collect', '0 */6 * * *', 0, 0, TRUE, :now, :now)
                """),
                {"topic_id": str(topic_id), "now": now},
            )
            logger.info(f"[Automation] 采集已开启 topic={topic_id}")
        else:
            # 关闭采集：移除调度器中的 collect job
            sched = get_scheduler()
            try:
                collect_job_name = f"collect_{topic_id}"
                sched.remove_job(collect_job_name)
                logger.info(f"[Automation] 采集已关闭 topic={topic_id}")
            except Exception:
                pass
            # 数据库更新（先删后插确保唯一性）
            await db.execute(
                text("DELETE FROM scheduled_jobs WHERE topic_id = :topic_id AND job_type = 'collect'"),
                {"topic_id": str(topic_id)},
            )
            now = datetime.utcnow()
            await db.execute(
                text("""
                    INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, created_at, updated_at)
                    VALUES (:topic_id, 'collect', '0 */6 * * *', 0, 0, FALSE, :now, :now)
                """),
                {"topic_id": str(topic_id), "now": now},
            )

    # 3. 处理报告启停
    if req.report_enabled is not None:
        if req.report_enabled:
            # 开启报告：按周期层次调度
            periods = _get_higher_periods(push_cycle)
            for idx, rtype in enumerate(periods):
                # 错开分钟，避免同时触发
                r_minute = minute + idx
                if r_minute >= 60:
                    r_minute = r_minute - 60
                schedule_report(
                    topic_id=topic_id,
                    org_id=org_id,
                    user_id=user_id,
                    report_type=rtype,
                    hour=hour,
                    minute=r_minute,
                )
                # 持久化（先删后插）
                now = datetime.utcnow()
                await db.execute(
                    text("DELETE FROM scheduled_jobs WHERE topic_id = :topic_id AND job_type = :job_type"),
                    {"topic_id": str(topic_id), "job_type": f"report_{rtype}"},
                )
                await db.execute(
                    text("""
                        INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, created_at, updated_at)
                        VALUES (:topic_id, :job_type, NULL, :hour, :minute, TRUE, :now, :now)
                    """),
                    {
                        "topic_id": str(topic_id),
                        "job_type": f"report_{rtype}",
                        "hour": hour,
                        "minute": r_minute,
                        "now": now,
                    },
                )
            logger.info(f"[Automation] 报告已开启 topic={topic_id} periods={periods}")
        else:
            # 关闭报告：移除所有 report_* job
            sched = get_scheduler()
            for rtype in _REPORT_HIERARCHY:
                try:
                    report_job_name = f"report_{rtype}_{topic_id}"
                    sched.remove_job(report_job_name)
                except Exception:
                    pass
            # 数据库更新（先删后插）
            await db.execute(
                text("DELETE FROM scheduled_jobs WHERE topic_id = :topic_id AND job_type LIKE 'report_%'"),
                {"topic_id": str(topic_id)},
            )
            now = datetime.utcnow()
            for rtype in _REPORT_HIERARCHY:
                # 只插一条 is_active=FALSE 的记录，保留历史
                pass
            logger.info(f"[Automation] 报告已关闭 topic={topic_id}")

    # 4. 处理飞书推送启停
    if req.feishu_push_enabled is not None:
        now = datetime.utcnow()
        # 检查是否存在配置
        existing = await db.execute(
            text("SELECT id FROM topic_push_configs WHERE topic_id = :topic_id"),
            {"topic_id": str(topic_id)},
        )
        if existing.fetchone():
            await db.execute(
                text("UPDATE topic_push_configs SET feishu_push_enabled = :enabled, updated_at = :now WHERE topic_id = :topic_id"),
                {"topic_id": str(topic_id), "enabled": req.feishu_push_enabled, "now": now},
            )
        else:
            # 没有配置就新建一条
            import uuid
            await db.execute(
                text("""
                    INSERT INTO topic_push_configs (id, topic_id, feishu_push_enabled, created_at, updated_at)
                    VALUES (:id, :topic_id, :enabled, :now, :now)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "topic_id": str(topic_id),
                    "enabled": req.feishu_push_enabled,
                    "now": now,
                },
            )
        logger.info(f"[Automation] 飞书推送 {'开启' if req.feishu_push_enabled else '关闭'} topic={topic_id}")

    await db.commit()

    # 5. 返回更新后的配置
    # 重新读取最新状态
    jobs_result = await db.execute(
        text("SELECT job_type, is_active FROM scheduled_jobs WHERE topic_id = :topic_id AND is_active = TRUE"),
        {"topic_id": str(topic_id)},
    )
    active_job_types = {j.job_type for j in jobs_result.fetchall()}

    push_check = await db.execute(
        text("SELECT feishu_push_enabled FROM topic_push_configs WHERE topic_id = :topic_id"),
        {"topic_id": str(topic_id)},
    )
    feishu_row = push_check.fetchone()
    feishu_enabled = bool(feishu_row and feishu_row.feishu_push_enabled)

    return TopicAutomationConfig(
        topic_id=str(topic_id),
        topic_name=topic_row.name if hasattr(topic_row, 'name') else "",
        category="",
        push_cycle=push_cycle,
        push_time=push_time,
        collect_enabled="collect" in active_job_types,
        report_enabled=any(jt.startswith("report_") for jt in active_job_types),
        feishu_push_enabled=feishu_enabled,
    )
