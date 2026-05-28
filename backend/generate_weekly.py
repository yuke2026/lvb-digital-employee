"""Generate weekly reports for all weekly-cycle topics."""
import asyncio, json, uuid
from datetime import datetime
import sys
sys.path.insert(0, '/home/ubuntu/lvb-digital-employee/backend')

from app.core.database import async_session
from app.api.v1.reports import _run_report_generation
from sqlalchemy import text

async def main():
    # Get all weekly topics
    async with async_session() as db:
        rows = await db.execute(
            text("SELECT id, name, org_id FROM topics WHERE push_cycle = 'weekly' AND is_active = 1")
        )
        topics = rows.fetchall()

    print(f"找到 {len(topics)} 个weekly主题")

    results = []
    for t in topics:
        topic_id = uuid.UUID(t[0])
        topic_name = t[1]
        org_id = uuid.UUID(t[2]) if t[2] else uuid.UUID("f4894b2f-c58d-4b7a-8fec-bc45e599bc3c")
        user_id = uuid.UUID("23497e11b9cc4339a6fd19e8f7e53d4e")

        print(f"\n=== 正在生成 {topic_name} 周报 ===")

        async with async_session() as db:
            report_id = uuid.uuid4()
            now = datetime.utcnow()

            await db.execute(
                text("""
                    INSERT INTO reports (id, topic_id, report_type, title, summary, push_time, status, created_at, updated_at)
                    VALUES (:id, :topic_id, :report_type, :title, :summary, :push_time, 'pending', :created_at, :updated_at)
                """),
                {
                    "id": str(report_id),
                    "topic_id": str(topic_id),
                    "report_type": "weekly",
                    "title": "周报 - 生成中...",
                    "summary": None,
                    "push_time": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await db.commit()

        # Now generate
        try:
            async with async_session() as db:
                await _run_report_generation(
                    report_id=report_id,
                    topic_id=topic_id,
                    report_type="weekly",
                    org_id=org_id,
                    user_id=user_id,
                    db=db,
                )
            results.append((topic_name, "OK"))
            print(f"  ✅ {topic_name} 周报生成成功")
        except Exception as e:
            import traceback
            results.append((topic_name, f"FAIL: {e}"))
            print(f"  ❌ {topic_name} 周报生成失败: {e}")
            traceback.print_exc()

    print("\n=== 结果汇总 ===")
    for name, status in results:
        print(f"  {name}: {status}")

asyncio.run(main())
