"""Regenerate 新能源汽车 weekly report with fewer articles."""
import asyncio, json, uuid
from datetime import datetime
import sys
sys.path.insert(0, '/home/ubuntu/lvb-digital-employee/backend')

from app.core.database import async_session
from sqlalchemy import text

async def main():
    topic_id = uuid.UUID("07879543-66f4-4490-b660-77c084f1feb8")
    topic_name = "新能源汽车行业动态"
    org_id = uuid.UUID("f4894b2f-c58d-4b7a-8fec-bc45e599bc3c")
    user_id = uuid.UUID("23497e11b9cc4339a6fd19e8f7e53d4e")

    # Delete old empty reports for this topic
    async with async_session() as db:
        await db.execute(text("""
            DELETE FROM reports
            WHERE topic_id = :tid AND report_type = 'weekly'
            AND created_at > '2026-05-27 04:00:00'
        """), {"tid": str(topic_id)})
        await db.commit()
        print("Deleted old empty reports")

    # Create placeholder with high max_tokens
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

    # Generate with fewer articles (limit to 20) and higher max_tokens
    print("Generating with 20 articles and 4096 max_tokens...")
    
    async with async_session() as db:
        # Fetch articles
        source_ids = await db.execute(
            text("SELECT source_id FROM topic_sources WHERE topic_id = :tid"),
            {"tid": str(topic_id)}
        )
        sid_rows = source_ids.fetchall()
        topic_source_ids = [str(r[0]) for r in sid_rows]

        start_date = (datetime.utcnow() - datetime(2026, 5, 25, 0, 0).replace()).days
        from datetime import timedelta
        week_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        days_since_monday = week_start.weekday()
        week_start = week_start - timedelta(days=days_since_monday)

        placeholders = ", ".join(f":s{i}" for i in range(len(topic_source_ids)))
        params = {f"s{i}": sid for i, sid in enumerate(topic_source_ids)}
        params["start_date"] = week_start
        params["end_date"] = datetime.utcnow()

        article_result = await db.execute(
            text(f"""
                SELECT id, title, content, summary, url, published_at, fetched_at
                FROM raw_articles
                WHERE source_id IN ({placeholders})
                  AND is_processed = true
                  AND published_at >= :start_date
                  AND published_at <= :end_date
                ORDER BY published_at DESC
                LIMIT 20
            """),
            params,
        )
        articles = article_result.fetchall()
        print(f"Found {len(articles)} articles (limited to 20)")

        # Build compact prompt
        import json as _json
        articles_data = [{
            "title": a.title,
            "content": (a.content or "")[:800],
            "summary": (a.summary or "")[:300],
            "url": a.url,
        } for a in articles]

        system_prompt = """你是一位资深的行业战略分析师。请基于以下文章，生成结构化的周度战略分析报告。

请严格以JSON格式返回：
{
    "s": "优势分析（300-500字，引用具体文章）",
    "w": "劣势分析（300-500字）",
    "o": "机会分析（300-500字）",
    "t": "威胁分析（300-500字）",
    "risks": [
        {"title": "风险名称", "description": "详细描述", "level": "高/中/低", "impact": "影响说明"}
    ],
    "opportunities": [
        {"title": "机会名称", "description": "详细描述", "potential": "潜力评估", "timeline": "时间窗口"}
    ],
    "risk_level": "整体风险等级",
    "key_trends": "关键趋势总结（400字以内）",
    "action_items": ["建议1", "建议2", "建议3"]
}

请确保返回完整的、格式正确的JSON。分析必须有实质内容，每项要求200字以上。"""

        user_prompt = f"""请基于以下 {len(articles)} 篇与「新能源汽车行业动态」相关的文章，生成周度战略分析报告：

{_json.dumps(articles_data, ensure_ascii=False, indent=2)}

请返回完整JSON。"""

        # Call DeepSeek with higher max_tokens
        from app.core.config import settings
        import httpx
        url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0.8,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            response = data["choices"][0]["message"]["content"]

        # Parse response
        content = response.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            parsed = _json.loads(content)
            print(f"Parse OK! SWOT has content: S={bool(parsed.get('s'))}, W={bool(parsed.get('w'))}, O={bool(parsed.get('o'))}, T={bool(parsed.get('t'))}")
            print(f"Risks: {len(parsed.get('risks', []))}, Opps: {len(parsed.get('opportunities', []))}")
        except Exception as e:
            print(f"Parse failed: {e}")
            print(f"Response (first 500): {response[:500]}")
            return

        # Save to DB
        swot = {"s": parsed.get("s", ""), "w": parsed.get("w", ""), "o": parsed.get("o", ""), "t": parsed.get("t", "")}
        risk_items = {"risks": parsed.get("risks", [])}
        opportunities = {"opportunities": parsed.get("opportunities", [])}
        risk_level = parsed.get("risk_level", "中")
        key_trends = parsed.get("key_trends", "")
        action_items = parsed.get("action_items", [])

        summary = f"「新能源汽车行业动态」周报共分析 {len(articles)} 篇相关文章（{week_start.strftime('%Y年第%U周')}）"
        if parsed.get("key_trends"):
            summary += f"；趋势：{parsed['key_trends'][:80]}"
        if parsed.get("risks"):
            summary += f"；识别到 {len(parsed['risks'])} 项风险"
        if parsed.get("opportunities"):
            summary += f"；发现 {len(parsed['opportunities'])} 项机会"

        source_articles = [{"id": str(a[0]), "title": a[1], "summary": (a[3] or "")[:200], "url": a[4] or ""} for a in articles]
        content_snapshot = {"articles": source_articles, "time_range": {"start": week_start.isoformat(), "end": datetime.utcnow().isoformat()}, "key_trends": key_trends, "action_items": action_items}

        from datetime import datetime as dt
        now = dt.utcnow()
        await db.execute(
            text("""
                UPDATE reports
                SET title = :title, summary = :summary, content = :content, swot = :swot,
                    risk_level = :risk_level, risk_items = :risk_items, opportunities = :opportunities,
                    push_time = :push_time, status = :status, updated_at = :updated_at
                WHERE id = :report_id
            """),
            {
                "report_id": str(report_id),
                "title": f"新能源汽车行业动态 - 周报 - 2026年第22周",
                "summary": summary,
                "content": _json.dumps(content_snapshot, ensure_ascii=False),
                "swot": _json.dumps(swot, ensure_ascii=False),
                "risk_level": risk_level,
                "risk_items": _json.dumps(risk_items, ensure_ascii=False),
                "opportunities": _json.dumps(opportunities, ensure_ascii=False),
                "push_time": now,
                "status": "generated",
                "updated_at": now,
            },
        )
        await db.commit()
        print("✅ 新能源汽车周报保存成功")

asyncio.run(main())
