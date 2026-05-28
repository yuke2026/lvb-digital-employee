"""Final article processing: mark articles that match ANY topic keyword."""
import asyncio
import json

from sqlalchemy import text
from app.core.database import async_session

ORG_ID = "f4894b2f-c58d-4b7a-8fec-bc45e599bc3c"


async def main():
    async with async_session() as db:
        # Get topics with parsed keywords
        result = await db.execute(
            text("SELECT id, name, keywords FROM topics WHERE org_id = :org_id"),
            {"org_id": ORG_ID},
        )
        topics = result.fetchall()

        all_keywords = {}  # topic_id -> [keywords]
        for t in topics:
            raw_kws = t[2]
            kws = []
            if raw_kws:
                try:
                    parsed = json.loads(raw_kws) if isinstance(raw_kws, str) else raw_kws
                    if isinstance(parsed, list):
                        if len(parsed) == 1 and "，" in str(parsed[0]):
                            kws = [k.strip() for k in parsed[0].split("，") if k.strip()]
                        elif len(parsed) == 1 and "、" in str(parsed[0]):
                            kws = [k.strip() for k in parsed[0].split("、") if k.strip()]
                        else:
                            kws = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            all_keywords[str(t[0])] = (str(t[1]), kws)

        # Get all source IDs
        result = await db.execute(text("SELECT id FROM news_sources WHERE org_id = :org_id"), {"org_id": ORG_ID})
        all_source_ids = [str(r[0]) for r in result.fetchall()]
        s_ph = ", ".join(f":s{i}" for i in range(len(all_source_ids)))
        s_params = {f"s{i}": sid for i, sid in enumerate(all_source_ids)}

        # Reset all articles to unprocessed
        await db.execute(
            text(f"UPDATE raw_articles SET is_processed = 0, summary = NULL WHERE source_id IN ({s_ph})"),
            s_params,
        )
        await db.commit()

        # Get all articles
        result = await db.execute(
            text(f"SELECT id, title, content, source_id FROM raw_articles WHERE source_id IN ({s_ph})"),
            s_params,
        )
        articles = result.fetchall()
        print(f"📊 Total articles: {len(articles)}")

        # For each article, check if it matches ANY topic's keywords
        matched_count = 0
        match_summary = {}  # topic_id -> count

        for art in articles:
            art_id = str(art[0])
            title = str(art[1] or "")
            content = str(art[2] or "")
            src_id = str(art[3])
            text_content = f"{title} {content}".lower()

            matching_topics = []
            for tid, (tname, kws) in all_keywords.items():
                if kws and any(kw.lower() in text_content for kw in kws):
                    matching_topics.append(tname)

            if matching_topics:
                await db.execute(
                    text("UPDATE raw_articles SET is_processed = 1, summary = :summary WHERE id = :id"),
                    {"id": art_id, "summary": "匹配: " + ", ".join(matching_topics[:3])},
                )
                matched_count += 1
                for tname in matching_topics:
                    for tid, (tn, _) in all_keywords.items():
                        if tn == tname:
                            match_summary[tid] = match_summary.get(tid, 0) + 1

        await db.commit()

        print(f"\n✅ Matched: {matched_count}/{len(articles)} articles")
        for tid, (tname, _) in all_keywords.items():
            c = match_summary.get(tid, 0)
            print(f"   • {tname}: {c} matching articles")

        # Show sample
        result = await db.execute(
            text("""
                SELECT title, summary FROM raw_articles
                WHERE is_processed = 1 AND summary IS NOT NULL
                LIMIT 10
            """),
        )
        print(f"\n📰 Sample matched articles:")
        for r in result.fetchall():
            print(f"   • {str(r[0])[:50]}")

        # Clean old reports
        await db.execute(text("DELETE FROM reports"))
        await db.commit()

        # Generate fresh reports
        print(f"\n📊 Generating reports...")
        for tid, (tname, kws) in all_keywords.items():
            from datetime import datetime, timedelta
            import uuid

            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)

            r = await db.execute(
                text("""
                    SELECT COUNT(*) FROM raw_articles
                    WHERE is_processed = 1 AND fetched_at >= :yesterday
                """),
                {"yesterday": yesterday},
            )
            art_count = r.fetchone()[0]

            summary = f"本日报共分析 {art_count} 篇相关文章" if art_count > 0 else "本日报时间范围内无已处理的文章数据"
            status = "generated" if art_count > 0 else "draft"

            report_id = str(uuid.uuid4())
            await db.execute(
                text("""
                    INSERT INTO reports
                        (id, topic_id, report_type, title, summary, content,
                         swot, risk_level, risk_items, opportunities,
                         push_time, status, created_at, updated_at)
                    VALUES
                        (:id, :topic_id, :report_type, :title, :summary, NULL,
                         :swot, :risk_level, :risk_items, :opportunities,
                         :push_time, :status, :now, :now)
                """),
                {
                    "id": report_id, "topic_id": tid, "report_type": "daily",
                    "title": f"日报 - {now.strftime('%Y-%m-%d')}",
                    "summary": summary,
                    "swot": json.dumps({"s": "", "w": "", "o": "", "t": ""}),
                    "risk_level": "中",
                    "risk_items": json.dumps({"risks": []}),
                    "opportunities": json.dumps({"opportunities": []}),
                    "push_time": now,
                    "status": status,
                    "now": now,
                },
            )
            await db.commit()
            print(f"   ✅ {tname}: {art_count} articles - {summary[:40]}...")

    print("\n🎉 Complete!")


if __name__ == "__main__":
    asyncio.run(main())
