"""Push all weekly reports to Feishu."""
import asyncio, json, uuid
from datetime import datetime
import sys
sys.path.insert(0, '/home/ubuntu/lvb-digital-employee/backend')

from app.core.database import async_session
from app.services.push_service import push_report_full
from app.services.feishu_doc_push import push_report_to_feishu_with_retry
from sqlalchemy import text

FEISHU_CHAT_ID = "oc_a71f31ced2ba2e6c156c302a97d7df84"

async def main():
    async with async_session() as db:
        # Get latest weekly reports
        rows = await db.execute(
            text("""
                SELECT t.name, r.id, r.title, r.summary, r.swot, r.risk_level, r.risk_items, r.opportunities
                FROM reports r
                JOIN topics t ON t.id = r.topic_id
                WHERE r.report_type = 'weekly'
                AND r.status = 'generated'
                AND r.created_at IN (
                    SELECT MAX(r2.created_at) FROM reports r2
                    WHERE r2.report_type = 'weekly' AND r2.status = 'generated'
                    GROUP BY r2.topic_id
                )
                ORDER BY t.name
            """)
        )
        reports = rows.fetchall()

    if not reports:
        print("No weekly reports found!")
        return

    print(f"Found {len(reports)} weekly reports to push:")
    for r in reports:
        print(f"  {r[0]}: {r[2]}")

    results = []
    for r in reports:
        topic_name, report_id, title, summary, swot, risk_level, risk_items, opportunities = r
        
        print(f"\n=== Pushing: {topic_name} ===")
        
        report_data = {
            "feishu_doc_token": None,
            "report_type": "weekly",
            "title": title,
            "summary": summary,
            "swot": json.loads(swot) if swot else {},
            "risk_level": risk_level or "中",
            "risk_items": json.loads(risk_items) if risk_items else {"risks": []},
            "opportunities": json.loads(opportunities) if opportunities else {"opportunities": []},
        }

        try:
            result = await push_report_full(
                report_id=uuid.UUID(report_id),
                report_data=report_data,
                feishu_chat_id=FEISHU_CHAT_ID,
            )
            print(f"  ✅ Pushed: doc_token={result.get('feishu_doc_token')}")
            if result.get('feishu_doc_url'):
                print(f"  📄 URL: {result['feishu_doc_url']}")
            if result.get('errors'):
                print(f"  ⚠️ Errors: {result['errors']}")
            results.append((topic_name, "OK", result))
        except Exception as e:
            import traceback
            print(f"  ❌ Failed: {e}")
            traceback.print_exc()
            results.append((topic_name, f"FAIL: {e}", {}))

    print("\n" + "="*50)
    print("=== 推送结果汇总 ===")
    for name, status, res in results:
        print(f"  {name}: {status}")
        if res.get('feishu_doc_url'):
            print(f"    URL: {res['feishu_doc_url']}")

asyncio.run(main())
