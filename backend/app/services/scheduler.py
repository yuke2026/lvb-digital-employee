"""定时调度服务 - 使用 APScheduler 管理采集和报告生成任务"""
import logging
from datetime import datetime
from typing import Optional
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.base import JobLookupError

logger = logging.getLogger(__name__)

# 全局调度器实例（单例）
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """获取或创建全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return _scheduler


def start_scheduler():
    """启动调度器（应仅调用一次）"""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("APScheduler 调度器已启动")


def stop_scheduler():
    """停止调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 调度器已停止")


# ===== Job 名称常量 =====
JOB_COLLECT = "collect_{topic_id}"          # 采集任务
JOB_REPORT_DAILY = "report_daily_{topic_id}"  # 日报生成任务
JOB_REPORT_WEEKLY = "report_weekly_{topic_id}"  # 周报生成任务
JOB_REPORT_MONTHLY = "report_monthly_{topic_id}"  # 月报生成任务


def _collect_job_name(topic_id: uuid.UUID) -> str:
    return JOB_COLLECT.format(topic_id=str(topic_id))


def _report_job_name(topic_id: uuid.UUID, report_type: str) -> str:
    return f"report_{report_type}_{topic_id}"


# ===== 任务函数（被调度器调用）=====

async def _run_collect(topic_id: uuid.UUID, org_id: uuid.UUID):
    """执行指定主题的采集任务"""
    from app.services.rss_collector import collect_for_topic
    from app.services.article_processor import process_topic_articles
    try:
        logger.info(f"[Scheduler] 开始采集 topic={topic_id}")
        articles = await collect_for_topic(topic_id, org_id)
        logger.info(f"[Scheduler] 采集完成，获得 {len(articles)} 篇文章")

        if articles:
            await process_topic_articles(topic_id, org_id)
            logger.info(f"[Scheduler] 文章处理完成 topic={topic_id}")
    except Exception as e:
        logger.error(f"[Scheduler] 采集任务失败 topic={topic_id}: {e}", exc_info=True)


async def _run_report(
    topic_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    report_type: str,
):
    """执行指定主题的报告生成任务"""
    from app.services.report_generator import generate_report
    from app.models.report import Report
    from sqlalchemy import text
    from app.core.database import async_session
    try:
        logger.info(f"[Scheduler] 开始生成报告 topic={topic_id} type={report_type}")
        report_data = await generate_report(
            topic_id=topic_id,
            report_type=report_type,
            org_id=org_id,
            user_id=user_id,
        )
        now = datetime.utcnow()
        async with async_session() as db:
            result = await db.execute(
                text("""
                    INSERT INTO reports (topic_id, report_type, title, summary, content,
                                         swot, risk_level, risk_items, opportunities,
                                         push_time, status, created_at, updated_at)
                    VALUES (:topic_id, :report_type, :title, :summary, :content,
                            :swot, :risk_level, :risk_items, :opportunities,
                            :push_time, :status, :created_at, :updated_at)
                    RETURNING id
                """),
                {
                    "topic_id": str(topic_id),
                    "report_type": report_type,
                    "title": report_data.get("title", ""),
                    "summary": report_data.get("summary"),
                    "content": report_data.get("content"),
                    "swot": report_data.get("swot"),
                    "risk_level": report_data.get("risk_level"),
                    "risk_items": report_data.get("risk_items"),
                    "opportunities": report_data.get("opportunities"),
                    "push_time": report_data.get("push_time"),
                    "status": report_data.get("status", "generated"),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await db.commit()
            row = result.fetchone()
            report_id = row[0] if row else None
            logger.info(f"[Scheduler] 报告生成完成 report_id={report_id}")

            # 推送到飞书（如已配置）
            if report_data.get("feishu_doc_token"):
                logger.info(f"[Scheduler] 飞书文档已存在: {report_data['feishu_doc_token']}")
    except Exception as e:
        logger.error(f"[Scheduler] 报告生成任务失败 topic={topic_id}: {e}", exc_info=True)


# ===== 调度管理 API =====

def schedule_collect(
    topic_id: uuid.UUID,
    org_id: uuid.UUID,
    cron_expr: str = "0 */6 * * *",  # 默认每6小时
):
    """
    为指定主题添加采集任务。

    Args:
        topic_id: 主题 ID
        org_id: 组织 ID
        cron_expr: 标准 cron 表达式（6位：分 时 日 月 周 年）
    """
    sched = get_scheduler()
    job_name = _collect_job_name(topic_id)

    # 移除旧任务（防止重复）
    try:
        sched.remove_job(job_name)
        logger.info(f"[Scheduler] 移除旧采集任务: {job_name}")
    except JobLookupError:
        pass

    # 解析 cron 表达式（支持5位和6位）
    parts = cron_expr.split()
    if len(parts) == 5:
        # 标准5位: 分 时 日 月 周
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, timezone="Asia/Shanghai",
        )
    else:
        # 6位: 分 时 日 月 周 年
        minute, hour, day, month, day_of_week, year = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, year=year, timezone="Asia/Shanghai",
        )

    sched.add_job(
        _run_collect,
        trigger=trigger,
        args=[topic_id, org_id],
        id=job_name,
        name=f"采集任务 [{topic_id}]",
        replace_existing=True,
    )
    logger.info(f"[Scheduler] 添加采集任务: {job_name} cron={cron_expr}")


def schedule_report(
    topic_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    report_type: str = "daily",
    hour: int = 8,
    minute: int = 0,
):
    """
    为指定主题添加报告生成定时任务。

    Args:
        topic_id: 主题 ID
        org_id: 组织 ID
        user_id: 触发用户 ID
        report_type: daily | weekly | monthly
        hour: 推送小时（24小时制）
        minute: 推送分钟
    """
    sched = get_scheduler()
    job_name = _report_job_name(topic_id, report_type)

    try:
        sched.remove_job(job_name)
    except JobLookupError:
        pass

    # 日报：每天触发；周报：每周一；月报：每月1日
    if report_type == "daily":
        trigger = CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai")
    elif report_type == "weekly":
        # day_of_week=0 = 周一
        trigger = CronTrigger(hour=hour, minute=minute, day_of_week="mon", timezone="Asia/Shanghai")
    elif report_type == "monthly":
        # day=1 = 每月1日
        trigger = CronTrigger(hour=hour, minute=minute, day=1, timezone="Asia/Shanghai")
    else:
        raise ValueError(f"未知报告类型: {report_type}")

    sched.add_job(
        _run_report,
        trigger=trigger,
        args=[topic_id, org_id, user_id, report_type],
        id=job_name,
        name=f"{report_type}报告 [{topic_id}]",
        replace_existing=True,
    )
    logger.info(f"[Scheduler] 添加报告任务: {job_name} type={report_type} at {hour:02d}:{minute:02d}")


def remove_topic_jobs(topic_id: uuid.UUID):
    """移除与指定主题相关的所有调度任务"""
    sched = get_scheduler()
    for prefix in [JOB_COLLECT, "report_daily", "report_weekly", "report_monthly"]:
        job_name = f"{prefix}_{topic_id}"
        try:
            sched.remove_job(job_name)
            logger.info(f"[Scheduler] 移除任务: {job_name}")
        except JobLookupError:
            pass


def list_scheduled_jobs() -> list[dict]:
    """列出所有已调度的任务"""
    sched = get_scheduler()
    jobs = []
    for job in sched.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
