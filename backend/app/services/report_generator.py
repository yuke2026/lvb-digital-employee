"""Report generation service - generates SWOT analysis, risk assessment, and opportunities from processed articles."""
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report import Report
from app.models.report_item import ReportItem
from app.models.raw_article import RawArticle
from app.services.ai import chat_with_deepseek


async def _get_date_range(report_type: str) -> tuple[datetime, datetime]:
    """Calculate start and end datetime based on report type."""
    end_date = datetime.utcnow()
    if report_type == "daily":
        start_date = end_date - timedelta(days=1)
    elif report_type == "weekly":
        start_date = end_date - timedelta(weeks=1)
    elif report_type == "monthly":
        start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date - timedelta(days=1)
    return start_date, end_date


async def _fetch_articles_for_topic(
    db: AsyncSession,
    topic_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> list[RawArticle]:
    """Fetch processed articles for a topic within date range."""
    stmt = select(RawArticle).where(
        and_(
            RawArticle.is_processed == True,
            RawArticle.fetched_at >= start_date,
            RawArticle.fetched_at <= end_date,
        )
    ).order_by(RawArticle.fetched_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _build_swot_prompt(articles: list[RawArticle], report_type: str) -> tuple[str, str]:
    """Build system prompt and user prompt for SWOT analysis."""
    system_prompt = """你是一位专业的战略分析顾问，擅长对新闻文章进行深度分析，识别关键事件、风险和机会。

你的职责：
1. 从大量文章中提取核心信息和关键事件
2. 分析优势(Strengths)、劣势(Weaknesses)、机会(Opportunities)、威胁(Threats)
3. 识别风险因素并评估风险等级
4. 发现潜在的商业机会并评估其潜力

请始终以JSON格式返回分析结果。"""

    # Build articles content
    articles_content = []
    for article in articles:
        articles_content.append({
            "title": article.title,
            "content": (article.content or "")[:2000],
            "summary": article.summary or "",
            "url": article.url,
            "fetched_at": article.fetched_at.isoformat() if article.fetched_at else "",
        })

    articles_json = json.dumps(articles_content, ensure_ascii=False, indent=2)

    type_map = {"daily": "日", "weekly": "周", "monthly": "月"}
    type_label = type_map.get(report_type, "日")

    user_prompt = f"""请分析以下文章内容，生成{type_label}度战略分析报告。

## 文章列表
{articles_json}

## 输出要求
请严格以以下JSON格式返回分析结果，不要包含任何其他内容：

{{
    "s": "优势分析（基于文章内容提取，100字以内）",
    "w": "劣势分析（基于文章内容提取，100字以内）",
    "o": "机会分析（基于文章内容提取，100字以内）",
    "t": "威胁分析（基于文章内容提取，100字以内）",
    "risks": [
        {{
            "title": "风险名称（20字以内）",
            "description": "风险描述（50字以内）",
            "level": "高/中/低",
            "impact": "影响说明（30字以内）"
        }}
    ],
    "opportunities": [
        {{
            "title": "机会名称（20字以内）",
            "description": "机会描述（50字以内）",
            "potential": "潜力评估（20字以内）",
            "timeline": "时间窗口（20字以内）"
        }}
    ],
    "risk_level": "整体风险等级：高/中/低"
}}

请直接返回JSON，不要添加任何解释或说明。"""

    return system_prompt, user_prompt


async def _parse_swot_response(content: str) -> dict:
    """Parse DeepSeek response and extract SWOT data."""
    try:
        # Try to extract JSON from the response
        content = content.strip()
        # Handle cases where DeepSeek might wrap JSON in code blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
        return {
            "s": data.get("s", ""),
            "w": data.get("w", ""),
            "o": data.get("o", ""),
            "t": data.get("t", ""),
            "risks": data.get("risks", []),
            "opportunities": data.get("opportunities", []),
            "risk_level": data.get("risk_level", "中"),
        }
    except json.JSONDecodeError:
        # Return default structure if parsing fails
        return {
            "s": "（分析生成失败）",
            "w": "（分析生成失败）",
            "o": "（分析生成失败）",
            "t": "（分析生成失败）",
            "risks": [],
            "opportunities": [],
            "risk_level": "中",
        }


async def _create_report_items(
    db: AsyncSession,
    report: Report,
    articles: list[RawArticle],
    swot_data: dict,
) -> list[ReportItem]:
    """Create ReportItem records for each article."""
    risk_titles = {r.get("title", "") for r in swot_data.get("risks", [])}
    opp_titles = {o.get("title", "") for o in swot_data.get("opportunities", [])}

    report_items = []
    for article in articles:
        # Determine if this article is a key event
        is_key = any(
            keyword in article.title
            for keyword in ["重大", "突破", "危机", "转折", "首发", "独家"]
        )

        # Assign importance based on content length and key event status
        importance = 50
        if is_key:
            importance += 30
        if article.content and len(article.content) > 1000:
            importance += 10
        if article.summary and len(article.summary) > 100:
            importance += 10
        importance = min(importance, 100)

        # Assign tag based on content
        tag = None
        article_text = f"{article.title} {article.summary or ''} {article.content or ''}"
        if any(k in article_text for k in ["风险", "危机", "问题", "下滑"]):
            tag = "风险相关"
        elif any(k in article_text for k in ["机会", "增长", "突破", "扩张"]):
            tag = "机会相关"
        elif is_key:
            tag = "重大事件"

        report_item = ReportItem(
            report_id=report.id,
            article_id=article.id,
            title=article.title,
            summary=article.summary,
            importance=importance,
            source_confidence=0.8,
            is_key_event=is_key,
            tag=tag,
        )
        db.add(report_item)
        report_items.append(report_item)

    await db.flush()
    return report_items


async def generate_report(
    db: AsyncSession,
    topic_id: uuid.UUID,
    report_type: str,
) -> Report:
    """Generate a report (daily/weekly/monthly) for a given topic.

    Analyzes processed articles using DeepSeek to generate SWOT analysis,
    risk assessment, and opportunities. Saves Report and ReportItem rows.

    Args:
        db: AsyncSession - database session
        topic_id: uuid.UUID - the topic to generate report for
        report_type: str - one of "daily", "weekly", "monthly"

    Returns:
        Report - the generated report with saved items

    Raises:
        ValueError: if report_type is not daily/weekly/monthly
    """
    if report_type not in ("daily", "weekly", "monthly"):
        raise ValueError(
            f"Invalid report_type: {report_type}. Must be one of: daily, weekly, monthly"
        )

    # Calculate date range
    start_date, end_date = await _get_date_range(report_type)

    # Fetch processed articles for the topic
    articles = await _fetch_articles_for_topic(db, topic_id, start_date, end_date)

    # Build SWOT analysis using DeepSeek
    swot_data = {
        "s": "",
        "w": "",
        "o": "",
        "t": "",
        "risks": [],
        "opportunities": [],
        "risk_level": "中",
    }
    summary = ""

    if articles:
        system_prompt, user_prompt = await _build_swot_prompt(articles, report_type)
        response = await chat_with_deepseek(system_prompt, [{"role": "user", "content": user_prompt}])
        swot_data = await _parse_swot_response(response)

        # Generate summary from articles
        summary_parts = [f"本{type_map.get(report_type, '日')}报共分析 {len(articles)} 篇相关文章"]
        if swot_data.get("s"):
            summary_parts.append(f"优势：{swot_data['s'][:50]}")
        if swot_data.get("o"):
            summary_parts.append(f"机会：{swot_data['o'][:50]}")
        if swot_data.get("risks"):
            summary_parts.append(f"识别到 {len(swot_data['risks'])} 项风险")
        if swot_data.get("opportunities"):
            summary_parts.append(f"发现 {len(swot_data['opportunities'])} 项机会")
        summary = "；".join(summary_parts)
    else:
        summary = f"本{type_map.get(report_type, '日')}报时间范围内无已处理的文章数据"

    # Determine report title
    type_label_map = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    type_label = type_label_map.get(report_type, "日报")
    report_title = f"{type_label} - {datetime.utcnow().strftime('%Y-%m-%d')}"

    # Create Report record
    report = Report(
        topic_id=topic_id,
        report_type=report_type,
        title=report_title,
        summary=summary,
        swot={
            "s": swot_data.get("s", ""),
            "w": swot_data.get("w", ""),
            "o": swot_data.get("o", ""),
            "t": swot_data.get("t", ""),
        },
        risk_level=swot_data.get("risk_level", "中"),
        risk_items={"risks": swot_data.get("risks", [])},
        opportunities={"opportunities": swot_data.get("opportunities", [])},
        status="draft" if not articles else "generated",
    )

    db.add(report)
    await db.flush()

    # Create ReportItem records for each article
    if articles:
        await _create_report_items(db, report, articles, swot_data)

    await db.commit()
    await db.refresh(report)

    return report


# Mapping for report type labels (used internally)
type_map = {"daily": "日", "weekly": "周", "monthly": "月"}
