"""Setup timed tasks: collect every 6h, daily report at 8 AM."""
import asyncio
import uuid
from datetime import datetime

from sqlalchemy import text
from app.core.database import async_session
from app.services.scheduler import (
    start_scheduler,
    schedule_collect,
    schedule_report,
    get_scheduler,
)

ORG_ID = "f4894b2f-c58d-4b7a-8fec-bc45e599bc3c"
USER_ID = "23497e11b9cc4339a6fd19e8f7e53d4e"  # admin


async def main():
    # Ensure scheduler is running
    start_scheduler()

    # Get all topics
    async with async_session() as db:
        result = await db.execute(
            text("SELECT id, name, push_cycle FROM topics WHERE org_id = :org_id"),
            {"org_id": ORG_ID},
        )
        topics = result.fetchall()

    print("📅 Setting up scheduled tasks...")
    print(f"   Found {len(topics)} topics\n")

    for t in topics:
        topic_id = uuid.UUID(str(t[0]))
        topic_name = t[1]
        push_cycle = t[2] or "daily"

        # 1. Collection: every 6 hours
        schedule_collect(
            topic_id=topic_id,
            org_id=uuid.UUID(ORG_ID),
            cron_expr="0 */6 * * *",  # Every 6 hours
        )
        print(f"   ✅ {topic_name}: 采集每6小时")

        # 2. Report generation: daily at 8:00
        schedule_report(
            topic_id=topic_id,
            org_id=uuid.UUID(ORG_ID),
            user_id=uuid.UUID(USER_ID),
            report_type=push_cycle,
            hour=8,
            minute=0,
        )
        print(f"   ✅ {topic_name}: {push_cycle}报告 08:00")

    # Also persist to scheduled_jobs table
    async with async_session() as db:
        now = datetime.utcnow()
        for t in topics:
            topic_id = str(t[0])
            # Collect job - delete first, then insert
            await db.execute(
                text("DELETE FROM scheduled_jobs WHERE topic_id = :tid AND job_type = 'collect'"),
                {"tid": topic_id},
            )
            await db.execute(
                text("""
                    INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, created_at, updated_at)
                    VALUES (:tid, 'collect', '0 */6 * * *', 0, 0, 1, :now, :now)
                """),
                {"tid": topic_id, "now": now},
            )
            # Report job
            await db.execute(
                text("DELETE FROM scheduled_jobs WHERE topic_id = :tid AND job_type = :job_type"),
                {"tid": topic_id, "job_type": f"report_{t[2] or 'daily'}"},
            )
            await db.execute(
                text("""
                    INSERT INTO scheduled_jobs (topic_id, job_type, cron_expr, hour, minute, is_active, created_at, updated_at)
                    VALUES (:tid, :job_type, NULL, 8, 0, 1, :now, :now)
                """),
                {"tid": topic_id, "job_type": f"report_{t[2] or 'daily'}", "now": now},
            )
        await db.commit()

    # Show running jobs
    print("\n📋 Current scheduled jobs:")
    sched = get_scheduler()
    for job in sched.get_jobs():
        print(f"   • {job.name} | next_run: {job.next_run_time}")

    print("\n🎉 Scheduling complete!")


if __name__ == "__main__":
    asyncio.run(main())
