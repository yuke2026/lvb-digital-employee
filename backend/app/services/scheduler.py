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
    """执行指定主题的采集任务（使用 raw SQL + feedparser 直接采集处理）"""
    from app.core.database import async_session
    from sqlalchemy import text
    import feedparser
    from datetime import datetime
    import json
    try:
        logger.info(f"[Scheduler] 开始采集 topic={topic_id}")
        async with async_session() as db:
            # 1. 获取主题信息（关键词等）
            topic_result = await db.execute(
                text("SELECT keywords, exclude_keywords FROM topics WHERE id = :topic_id"),
                {"topic_id": str(topic_id)},
            )
            topic_row = topic_result.fetchone()
            if not topic_row:
                logger.warning(f"[Scheduler] 主题不存在 topic={topic_id}")
                return

            keywords = json.loads(topic_row.keywords) if isinstance(topic_row.keywords, str) else (topic_row.keywords or [])
            exclude_keywords = json.loads(topic_row.exclude_keywords) if isinstance(topic_row.exclude_keywords, str) else (topic_row.exclude_keywords or [])

            # 2. 获取该主题关联的 RSS 源
            sources_result = await db.execute(
                text("""
                    SELECT ns.id, ns.url
                    FROM news_sources ns
                    JOIN topic_sources ts ON ts.source_id = ns.id
                    WHERE ts.topic_id = :topic_id
                      AND ns.source_type = 'rss'
                      AND ns.is_active = TRUE
                """),
                {"topic_id": str(topic_id)},
            )
            source_rows = sources_result.fetchall()

            if not source_rows:
                logger.info(f"[Scheduler] 主题 {topic_id} 没有关联的活跃 RSS 源")
                return

            # 3. 直接使用 feedparser 从各 RSS 源采集文章
            now = datetime.utcnow()
            total_articles = 0
            for src in source_rows:
                source_id, url = src
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    title = entry.get("title", "No title")
                    article_url = entry.get("link") or entry.get("id", "")
                    if not article_url:
                        continue

                    # 检查是否已存在（去重）
                    existing = await db.execute(
                        text("SELECT id FROM raw_articles WHERE source_id = :source_id AND url = :url"),
                        {"source_id": str(source_id), "url": article_url},
                    )
                    if existing.fetchone():
                        continue

                    # 提取内容
                    content = None
                    if hasattr(entry, "content") and entry.content:
                        content = entry.content[0].value
                    elif hasattr(entry, "summary"):
                        content = entry.summary

                    # 解析发布时间
                    published_at = None
                    for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
                        parsed = getattr(entry, date_field, None)
                        if parsed:
                            try:
                                published_at = datetime(*parsed[:6])
                                break
                            except (ValueError, TypeError):
                                continue

                    article_id = uuid.uuid4()
                    await db.execute(
                        text("""
                            INSERT INTO raw_articles
                                (id, source_id, url, title, content, summary,
                                 published_at, fetched_at, is_processed)
                            VALUES
                                (:id, :source_id, :url, :title, :content, :summary,
                                 :published_at, :fetched_at, FALSE)
                        """),
                        {
                            "id": str(article_id),
                            "source_id": str(source_id),
                            "url": article_url,
                            "title": title,
                            "content": content,
                            "summary": None,
                            "published_at": published_at,
                            "fetched_at": now,
                        },
                    )
                    total_articles += 1

                # 更新新闻源的最后抓取时间
                await db.execute(
                    text("UPDATE news_sources SET last_fetch_at = :now, last_fetch_status = 'success' WHERE id = :source_id"),
                    {"now": now, "source_id": str(source_id)},
                )

            await db.commit()
            logger.info(f"[Scheduler] 采集完成，获得 {total_articles} 篇文章 topic={topic_id}")

            # 4. 关键词匹配处理（标记已处理的文章）
            if total_articles > 0:
                from app.services.article_processor import process_unprocessed_articles
                processed = await process_unprocessed_articles(
                    db=db,
                    topic_id=topic_id,
                    keywords=keywords,
                    exclude_keywords=exclude_keywords,
                )
                logger.info(f"[Scheduler] 文章处理完成，已处理 {processed} 篇 topic={topic_id}")
            else:
                # 即使没有新文章，也处理可能积压的未处理文章
                from app.services.article_processor import process_unprocessed_articles
                processed = await process_unprocessed_articles(
                    db=db,
                    topic_id=topic_id,
                    keywords=keywords,
                    exclude_keywords=exclude_keywords,
                )
                if processed > 0:
                    logger.info(f"[Scheduler] 处理积压文章 {processed} 篇 topic={topic_id}")

    except Exception as e:
        logger.error(f"[Scheduler] 采集任务失败 topic={topic_id}: {e}", exc_info=True)


async def _run_report(
    topic_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    report_type: str,
):
    """执行指定主题的报告生成任务（使用改进的 _run_report_generation 逻辑）"""
    from app.api.v1.reports import _run_report_generation
    from app.core.database import async_session
    from sqlalchemy import text
    from datetime import datetime, timezone
    try:
        # ===== 重叠检查：同一日期内高周期报告覆盖低周期 =====
        now = datetime.now(timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Shanghai")
            local = now.astimezone(tz)
        except Exception:
            local = now
        is_first_of_month = local.day == 1
        is_monday = local.weekday() == 0  # 0 = Monday
        if is_first_of_month and report_type in ("daily", "weekly"):
            logger.info(f"[Scheduler] Skip {report_type} topic={topic_id}: covered by monthly on 1st")
            return
        if is_monday and not is_first_of_month and report_type == "daily":
            logger.info(f"[Scheduler] Skip daily topic={topic_id}: covered by weekly on Monday")
            return
        logger.info(f"[Scheduler] 开始生成报告 topic={topic_id} type={report_type}")

        async with async_session() as db:
            # Create a placeholder report record
            from uuid import uuid4
            from datetime import datetime
            now = datetime.utcnow()
            report_id = uuid4()

            await db.execute(
                text("""
                    INSERT INTO reports (id, topic_id, report_type, title, summary, push_time, status, created_at, updated_at)
                    VALUES (:id, :topic_id, :report_type, :title, :summary, :push_time, 'pending', :created_at, :updated_at)
                """),
                {
                    "id": str(report_id),
                    "topic_id": str(topic_id),
                    "report_type": report_type,
                    "title": f"{report_type}报告 - 生成中...",
                    "summary": None,
                    "push_time": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await db.commit()

        # Use the improved report generation logic from reports.py
        async with async_session() as db:
            await _run_report_generation(
                report_id=report_id,
                topic_id=topic_id,
                report_type=report_type,
                org_id=org_id,
                user_id=user_id,
                db=db,
            )
        logger.info(f"[Scheduler] 报告生成完成 report_id={report_id} type={report_type}")

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

    # 日报：每天触发；周报：每周一；月报：每月1日；季报：每季首月1日；年报：每年1月1日
    if report_type == "daily":
        trigger = CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai")
    elif report_type == "weekly":
        # day_of_week=0 = 周一
        trigger = CronTrigger(hour=hour, minute=minute, day_of_week="mon", timezone="Asia/Shanghai")
    elif report_type == "monthly":
        # day=1 = 每月1日
        trigger = CronTrigger(hour=hour, minute=minute, day=1, timezone="Asia/Shanghai")
    elif report_type == "quarterly":
        # month=1/4/7/10, day=1
        trigger = CronTrigger(hour=hour, minute=minute, month="1,4,7,10", day=1, timezone="Asia/Shanghai")
    elif report_type == "yearly":
        # month=1, day=1
        trigger = CronTrigger(hour=hour, minute=minute, month=1, day=1, timezone="Asia/Shanghai")
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


async def restore_jobs_from_db():
    """
    应用启动时从 scheduled_jobs 表恢复所有活跃任务到 APScheduler。
    """
    from app.core.database import async_session
    from sqlalchemy import text

    async with async_session() as db:
        result = await db.execute(
            text("SELECT topic_id, job_type, cron_expr, hour, minute FROM scheduled_jobs WHERE is_active = TRUE")
        )
        rows = result.fetchall()

    if not rows:
        logger.info("[Scheduler] 数据库中无活跃定时任务，跳过恢复")
        # 即使没有定时任务记录，也从 topics 表同步
        await sync_topic_schedules_from_db()
        return

    sched = get_scheduler()
    restored = 0
    for row in rows:
        topic_id = uuid.UUID(row.topic_id)
        job_type = row.job_type
        cron_expr = row.cron_expr
        hour = row.hour or 8
        minute = row.minute or 0

        try:
            if job_type == "collect" and cron_expr:
                schedule_collect(topic_id=topic_id, org_id=uuid.UUID("00000000-0000-0000-0000-000000000000"), cron_expr=cron_expr)
                restored += 1
            elif job_type.startswith("report_"):
                report_type = job_type.replace("report_", "")
                schedule_report(topic_id=topic_id, org_id=uuid.UUID("00000000-0000-0000-0000-000000000000"), user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"), report_type=report_type, hour=hour, minute=minute)
                restored += 1
        except Exception as e:
            logger.warning(f"[Scheduler] 恢复任务失败 topic={topic_id} type={job_type}: {e}")

    logger.info(f"[Scheduler] 已从数据库恢复 {restored} 个定时任务")

    # 同步 topics 表中的 push_cycle / push_time 到调度器
    await sync_topic_schedules_from_db()


async def sync_topic_schedules_from_db():
    """
    从 topics 表读取所有活跃主题的 push_cycle / push_time，
    自动注册对应的报告生成定时任务。
    如果没有配置 scheduled_jobs 记录，此函数确保主题的自动报告仍能按时生成。
    """
    from app.core.database import async_session
    from sqlalchemy import text
    import json as _json

    try:
        async with async_session() as db:
            result = await db.execute(
                text("""
                    SELECT id, org_id, push_cycle, push_time, is_active
                    FROM topics
                    WHERE is_active = TRUE
                """)
            )
            rows = result.fetchall()

        if not rows:
            logger.info("[AutoSchedule] 没有活跃主题需要调度")
            return

        scheduled = 0
        for row in rows:
            topic_id = uuid.UUID(row.id)
            org_id = uuid.UUID(row.org_id) if row.org_id else uuid.UUID("00000000-0000-0000-0000-000000000000")
            push_cycle = row.push_cycle or "daily"
            push_time = row.push_time or "08:30"
            is_active = row.is_active

            if not is_active:
                continue

            # Parse push_time "HH:MM"
            try:
                parts = push_time.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                hour, minute = 8, 30

            # Register report job based on push_cycle
            report_type = push_cycle  # push_cycle matches report type names
            user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

            # Also schedule higher-order periods
            # e.g. weekly → also monthly, quarterly, yearly
            #      monthly → also quarterly, yearly
            # 原则：向上兼容，不向下兼容
            hierarchy = ["daily", "weekly", "monthly", "quarterly", "yearly"]
            cycle_idx = hierarchy.index(report_type) if report_type in hierarchy else 0

            # Clean up stale lower-order jobs (e.g. daily jobs for weekly topics)
            for lower_idx in range(cycle_idx):
                stale_type = hierarchy[lower_idx]
                try:
                    sched = get_scheduler()
                    stale_job_name = f"report_{stale_type}_{topic_id}"
                    sched.remove_job(stale_job_name)
                except Exception:
                    pass

            # Schedule the base period + all higher periods
            for higher_type in hierarchy[cycle_idx:]:
                h_hour, h_minute = hour, minute
                # Stagger higher-period reports by 1 minute so they don't all fire at once
                if higher_type != report_type:
                    h_minute = (minute + hierarchy.index(higher_type)) % 60

                schedule_report(
                    topic_id=topic_id,
                    org_id=org_id,
                    user_id=user_id,
                    report_type=higher_type,
                    hour=h_hour,
                    minute=h_minute,
                )
            scheduled += len(hierarchy) - cycle_idx

        logger.info(f"[AutoSchedule] 已从 topics 同步 {scheduled} 个报告定时任务")

    except Exception as e:
        logger.error(f"[AutoSchedule] 同步失败: {e}", exc_info=True)
