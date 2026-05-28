"""Complete setup: fetch RSS, process articles, generate reports (all raw SQL)."""
import asyncio
import json
import uuid
import feedparser
from datetime import datetime, timedelta

from sqlalchemy import text
from app.core.database import async_session

ORG_ID = "f4894b2f-c58d-4b7a-8fec-bc45e599bc3c"

# RSS feeds
FEEDS = [
    ("573fde13-4fdc-43b8-abf3-b316fbd45919", "36kr", "https://www.36kr.com/feed"),
    ("ba1e2331-df97-471a-a183-343170e3cc95", "leiphone", "https://www.leiphone.com/feed"),
    ("a3de16dc-45aa-49c0-af4f-6798b4e1176c", "ithome", "https://www.ithome.com/rss/"),
]


async def fetch_articles_raw(source_id: str, source_name: str, feed_url: str) -> int:
    """Fetch RSS articles using raw feedparser + direct SQL insert."""
    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        print(f"   ❌ {source_name}: feed parse error")
        return 0

    now = datetime.utcnow()
    saved = 0

    async with async_session() as db:
        for entry in feed.entries:
            title = entry.get("title", "No title")
            url = entry.get("link") or entry.get("id", "")

            if not url:
                continue

            # Check for duplicate
            existing = await db.execute(
                text("SELECT 1 FROM raw_articles WHERE source_id = :sid AND url = :url"),
                {"sid": source_id, "url": url},
            )
            if existing.fetchone():
                continue

            # Extract content/summary
            content = None
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].value if entry.content else None
            if not content:
                if hasattr(entry, "summary_detail") and entry.summary_detail:
                    content = entry.summary_detail.value
                elif hasattr(entry, "summary"):
                    content = entry.summary

            summary = None
            if not content:
                summary = entry.get("summary")

            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6])
                except (ValueError, TypeError):
                    pass
            if not published and hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    published = datetime(*entry.updated_parsed[:6])
                except (ValueError, TypeError):
                    pass

            article_id = str(uuid.uuid4())
            await db.execute(
                text("""
                    INSERT INTO raw_articles
                        (id, source_id, url, title, content, summary,
                         published_at, fetched_at, language, is_processed)
                    VALUES
                        (:id, :source_id, :url, :title, :content, :summary,
                         :published_at, :fetched_at, 'zh', 0)
                """),
                {
                    "id": article_id,
                    "source_id": source_id,
                    "url": url,
                    "title": title,
                    "content": content,
                    "summary": summary,
                    "published_at": published,
                    "fetched_at": now,
                },
            )
            saved += 1

        # Update last_fetch
        await db.execute(
            text("UPDATE news_sources SET last_fetch_at = :now, last_fetch_status = 'success' WHERE id = :sid"),
            {"now": now, "sid": source_id},
        )
        await db.commit()

    return saved


def _keyword_filter(title: str, content: str | None, keywords: list[str], exclude: list[str]) -> bool:
    """Check if article matches at least one keyword and no exclude keyword."""
    text_content = f"{title} {content or ''}".lower()
    if keywords:
        if not any(kw.lower() in text_content for kw in keywords):
            return False
    if exclude:
        if any(kw.lower() in text_content for kw in exclude):
            return False
    return True


async def process_articles_raw(topic_id: str, topic_name: str, keywords: list[str]) -> int:
    """Process unprocessed articles for a topic: keyword filter + mark processed."""
    async with async_session() as db:
        # Get source IDs linked to this topic
        result = await db.execute(
            text("SELECT source_id FROM topic_sources WHERE topic_id = :tid"),
            {"tid": topic_id},
        )
        source_ids = [r[0] for r in result.fetchall()]
        if not source_ids:
            print(f"   ⚠ {topic_name}: no linked sources")
            return 0

        # Get unprocessed articles from these sources
        placeholders = ", ".join(f":s{i}" for i in range(len(source_ids)))
        params = {f"s{i}": sid for i, sid in enumerate(source_ids)}
        result = await db.execute(
            text(f"""
                SELECT id, title, content, url FROM raw_articles
                WHERE source_id IN ({placeholders}) AND is_processed = 0
                ORDER BY fetched_at DESC
            """),
            params,
        )
        rows = result.fetchall()

        if not rows:
            return 0

        processed = 0
        for row in rows:
            article_id, title, content, url = row
            if _keyword_filter(title, content, keywords, []):
                await db.execute(
                    text("UPDATE raw_articles SET is_processed = 1, summary = :summary WHERE id = :id"),
                    {"id": str(article_id), "summary": f"[{topic_name}] 匹配关键词"},
                )
                processed += 1
            else:
                # Mark as processed but no match (won't be used)
                await db.execute(
                    text("UPDATE raw_articles SET is_processed = 1 WHERE id = :id"),
                    {"id": str(article_id)},
                )

        await db.commit()
    return processed


async def generate_report_raw(topic_id: str, topic_name: str) -> dict:
    """Generate a report using raw SQL."""
    async with async_session() as db:
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        # Find processed articles in the last 24 hours
        result = await db.execute(
            text("""
                SELECT id, title, content, summary, url, fetched_at
                FROM raw_articles
                WHERE is_processed = 1 AND fetched_at >= :yesterday
                ORDER BY fetched_at DESC
                LIMIT 20
            """),
            {"yesterday": yesterday},
        )
        raw_articles = result.fetchall()

        article_list = []
        for r in raw_articles:
            article_list.append({
                "id": str(r[0]),
                "title": r[1],
                "content": (r[2] or "")[:500],
                "summary": r[3] or "",
                "url": r[4],
                "fetched_at": str(r[5]) if r[5] else "",
            })

        if raw_articles:
            summary = f"本日报共分析 {len(raw_articles)} 篇相关文章"
            status = "generated"
        else:
            summary = "本日报时间范围内无已处理的文章数据"
            status = "draft"

        report_id = str(uuid.uuid4())
        report_title = f"日报 - {now.strftime('%Y-%m-%d')}"
        swot = json.dumps({"s": "", "w": "", "o": "", "t": ""})
        risk_items = json.dumps({"risks": []})
        opportunities = json.dumps({"opportunities": []})

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
                "id": report_id,
                "topic_id": topic_id,
                "report_type": "daily",
                "title": report_title,
                "summary": summary,
                "swot": swot,
                "risk_level": "中",
                "risk_items": risk_items,
                "opportunities": opportunities,
                "push_time": now,
                "status": status,
                "now": now,
            },
        )
        await db.commit()

    return {
        "title": report_title,
        "summary": summary,
        "article_count": len(raw_articles),
        "status": status,
    }


async def main():
    # Step 1: Fetch RSS
    print("=" * 50)
    print("📡 Step 1: Fetching RSS feeds")
    print("=" * 50)
    total = 0
    for sid, name, url in FEEDS:
        count = await fetch_articles_raw(sid, name, url)
        total += count
        print(f"   {'✅' if count > 0 else '⚠'} {name}: {count} new articles")
    print(f"\n   Total: {total} articles fetched\n")

    # Step 2: Get topics
    async with async_session() as db:
        result = await db.execute(
            text("SELECT id, name, keywords FROM topics WHERE org_id = :org_id"),
            {"org_id": ORG_ID},
        )
        topics = result.fetchall()

    print("=" * 50)
    print("🔧 Step 2: Processing articles by topic")
    print("=" * 50)
    total_processed = 0
    for t in topics:
        topic_id = str(t[0])
        topic_name = t[1]
        raw_kws = t[2]

        # Parse keywords - split by Chinese comma if single element
        keywords = []
        if raw_kws:
            try:
                parsed = json.loads(raw_kws) if isinstance(raw_kws, str) else raw_kws
                if isinstance(parsed, list):
                    if len(parsed) == 1 and "，" in str(parsed[0]):
                        keywords = [k.strip() for k in parsed[0].split("，") if k.strip()]
                    elif len(parsed) == 1 and "，" not in str(parsed[0]) and "、" in str(parsed[0]):
                        keywords = [k.strip() for k in parsed[0].split("、") if k.strip()]
                    else:
                        keywords = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        print(f"\n📌 {topic_name}")
        print(f"   Keywords: {keywords}")

        count = await process_articles_raw(topic_id, topic_name, keywords)
        total_processed += count
        print(f"   Matched: {count} articles")

        if count > 0:
            # Show matched articles
            async with async_session() as db:
                result = await db.execute(
                    text("""
                        SELECT title FROM raw_articles
                        WHERE source_id IN (SELECT source_id FROM topic_sources WHERE topic_id = :tid)
                        AND is_processed = 1
                        ORDER BY fetched_at DESC LIMIT 5
                    """),
                    {"tid": topic_id},
                )
                for r in result.fetchall():
                    print(f"     • {r[0][:60]}")

    print(f"\n   Total processed: {total_processed}\n")

    # Step 3: Generate reports
    print("=" * 50)
    print("📊 Step 3: Generating daily reports")
    print("=" * 50)
    for t in topics:
        topic_id = str(t[0])
        topic_name = t[1]
        report = await generate_report_raw(topic_id, topic_name)
        print(f"\n📌 {topic_name}")
        print(f"   Status: {report['status']}")
        print(f"   Title: {report['title']}")
        print(f"   Summary: {report['summary']}")
        print(f"   Articles: {report['article_count']}")

    print("\n" + "=" * 50)
    print("🎉 Complete! Check the frontend at http://152.136.230.162:8000")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
