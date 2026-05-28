"""Save webhook URL and push all weekly reports to Feishu."""
import asyncio, json, uuid, httpx
from datetime import datetime
import sys
sys.path.insert(0, '/home/ubuntu/lvb-digital-employee/backend')

from app.core.database import async_session
from sqlalchemy import text

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/4ea2b377-2878-4ba4-b5d1-489ecb808773"

async def send_feishu_card(webhook_url: str, title: str, summary: str, swot: dict, risks: list, opportunities: list, risk_level: str, articles: list = None):
    """Send a Feishu interactive card via webhook."""
    # Build risk items text
    risk_text = ""
    for r in risks[:5]:  # Top 5 risks
        level_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}
        icon = level_icon.get(r.get("level", ""), "⚪")
        risk_text += f"**{icon} {r.get('title', '')}**\n{r.get('description', '')[:100]}\n\n"

    opp_text = ""
    for o in opportunities[:5]:  # Top 5 opportunities
        opp_text += f"**✅ {o.get('title', '')}**\n{o.get('description', '')[:100]}\n\n"

    # SWOT
    s = swot.get("s", "")[:200]
    w = swot.get("w", "")[:200]
    o = swot.get("o", "")[:200]
    t = swot.get("t", "")[:200]

    level_color = {"高": "red", "中": "yellow", "低": "green"}
    color = level_color.get(risk_level, "blue")

    # Build article list (top 10 links)
    article_links = ""
    if articles:
        for i, art in enumerate(articles[:10], 1):
            url = art.get("url", "")
            title_text = art.get("title", "无标题")[:50]
            if url:
                article_links += f"[{i}. {title_text}]({url})\n"
            else:
                article_links += f"{i}. {title_text}\n"

    elements = [
        {
            "tag": "markdown",
            "content": f"**📋 摘要**\n{summary[:400]}"
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"**💪 优势**\n{s[:300]}\n\n**⚠️ 劣势**\n{w[:300]}\n\n**🚀 机会**\n{o[:300]}\n\n**🔻 威胁**\n{t[:300]}"
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"**🔴 风险（{len(risks)}项）**\n{risk_text[:800] if risk_text else '暂无'}"
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"**✅ 机会（{len(opportunities)}项）**\n{opp_text[:800] if opp_text else '暂无'}"
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"**整体风险等级：{risk_level}**"
        },
    ]

    # Add article snapshot section
    if article_links:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "markdown",
            "content": f"**📰 源文章快照（{len(articles)}篇）**\n\n{article_links[:1500]}"
        })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 {title}"},
            "template": color,
        },
        "elements": elements,
    }

    payload = {"msg_type": "interactive", "card": card}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
        return resp.json()

async def main():
    # 1. Save webhook URL to all topic_push_configs
    async with async_session() as db:
        # Update all topics with the webhook URL
        await db.execute(
            text("UPDATE topic_push_configs SET webhook_url = :url"),
            {"url": WEBHOOK_URL}
        )
        await db.commit()
        print("✅ Webhook URL saved to all topic_push_configs")

    # 2. Get all weekly reports with full content
    async with async_session() as db:
        rows = await db.execute(
            text("""
                SELECT t.name, r.title, r.summary, r.swot, r.risk_level, r.risk_items, r.opportunities, r.content
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

    print(f"\n📤 Pushing {len(reports)} weekly reports to Feishu...")

    for r in reports:
        topic_name, title, summary, swot_json, risk_level, risks_json, opps_json, content_json = r
        
        swot = json.loads(swot_json) if swot_json else {}
        risks = json.loads(risks_json).get("risks", []) if risks_json else []
        opportunities = json.loads(opps_json).get("opportunities", []) if opps_json else []
        articles = []
        if content_json:
            try:
                content_data = json.loads(content_json)
                articles = content_data.get("articles", [])
            except Exception:
                articles = []

        print(f"\n=== Pushing: {topic_name} ===")
        print(f"    Risks: {len(risks)}, Opportunities: {len(opportunities)}, Articles: {len(articles)}")

        try:
            result = await send_feishu_card(
                WEBHOOK_URL, title, summary, swot, risks, opportunities, risk_level or "中",
                articles=articles,
            )
            print(f"    ✅ Sent! code={result.get('code')}")
        except Exception as e:
            print(f"    ❌ Failed: {e}")

    print("\n✅ All done!")

asyncio.run(main())
