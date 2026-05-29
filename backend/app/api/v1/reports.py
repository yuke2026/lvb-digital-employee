"""Reports CRUD router"""
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional

import feedparser
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["报告"])


# ===== Inline schemas =====

class ReportCreateRequest(BaseModel):
    topic_id: UUID
    report_type: str = Field(..., max_length=20)


class ReportResponse(BaseModel):
    id: UUID
    topic_id: UUID
    report_type: str
    title: str
    summary: Optional[str] = None
    content: Optional[dict] = None
    swot: Optional[dict] = None
    risk_level: Optional[str] = None
    risk_items: Optional[dict] = None
    opportunities: Optional[dict] = None
    push_time: Optional[datetime] = None
    status: str
    feishu_doc_token: Optional[str] = None
    feishu_msg_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ===== Helpers =====

async def _row_to_report(row) -> ReportResponse:
    def _j(v):
        """Parse JSON string from DB if needed."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return v
        return v

    return ReportResponse(
        id=row.id,
        topic_id=row.topic_id,
        report_type=row.report_type,
        title=row.title,
        summary=row.summary,
        content=_j(row.content),
        swot=_j(row.swot),
        risk_level=row.risk_level,
        risk_items=_j(row.risk_items),
        opportunities=_j(row.opportunities),
        push_time=row.push_time,
        status=row.status,
        feishu_doc_token=row.feishu_doc_token,
        feishu_msg_id=row.feishu_msg_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ===== Background task =====

async def _run_report_generation(
    report_id: UUID,
    topic_id: UUID,
    report_type: str,
    org_id: UUID,
    user_id: UUID,
    db: AsyncSession,
):
    """Background task: generate report content and update the report row."""
    import logging
    import json
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)
    try:
        # 1. Build date range (calendar periods, not "last N days")
        now_utc = datetime.utcnow()
        end_date = now_utc

        if report_type == "daily":
            # Today from 00:00 UTC
            start_date = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        elif report_type == "weekly":
            # This Monday 00:00 UTC
            days_since_monday = now_utc.weekday()  # Monday=0
            start_date = (now_utc - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0)
        elif report_type == "monthly":
            # This month 1st 00:00 UTC
            start_date = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif report_type == "quarterly":
            # This quarter start (month 1/4/7/10)
            quarter_month = ((now_utc.month - 1) // 3) * 3 + 1
            start_date = now_utc.replace(month=quarter_month, day=1,
                                         hour=0, minute=0, second=0, microsecond=0)
        elif report_type == "yearly":
            # This year Jan 1
            start_date = now_utc.replace(month=1, day=1,
                                         hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = now_utc - timedelta(days=1)

        # 2. Get topic info (name + keywords) and linked source IDs
        topic_info = await db.execute(
            text("SELECT name, keywords FROM topics WHERE id = :topic_id"),
            {"topic_id": str(topic_id)},
        )
        topic_row = topic_info.fetchone()
        topic_name = topic_row.name if topic_row else f"Topic-{topic_id}"
        topic_keywords_raw = topic_row.keywords if topic_row else "[]"

        # Parse keywords
        import json as _json
        try:
            topic_keywords = _json.loads(topic_keywords_raw) if isinstance(topic_keywords_raw, str) else (topic_keywords_raw or [])
        except Exception:
            topic_keywords = []

        # Get source IDs linked to this topic
        source_ids_result = await db.execute(
            text("SELECT source_id FROM topic_sources WHERE topic_id = :topic_id"),
            {"topic_id": str(topic_id)},
        )
        topic_source_ids = [str(r[0]) for r in source_ids_result.fetchall()]

        # 3. Fetch articles: only from topic-linked sources that match topic keywords
        if topic_source_ids:
            placeholders = ", ".join(f":s{i}" for i in range(len(topic_source_ids)))
            params = {f"s{i}": sid for i, sid in enumerate(topic_source_ids)}
            params["start_date"] = start_date
            params["end_date"] = end_date

            articles_result = await db.execute(
                text(f"""
                    SELECT id, title, content, summary, url, published_at, fetched_at
                    FROM raw_articles
                    WHERE source_id IN ({placeholders})
                      AND is_processed = true
                      AND published_at >= :start_date
                      AND published_at <= :end_date
                    ORDER BY published_at DESC
                """),
                params,
            )
            all_article_rows = articles_result.fetchall()
        else:
            all_article_rows = []

        # Filter articles by keyword match (in Python for flexibility)
        article_rows = []
        for a in all_article_rows:
            text_content = f"{a.title or ''} {a.content or ''} {a.summary or ''}".lower()
            if topic_keywords:
                # Article must match at least one keyword
                if any(kw.lower() in text_content for kw in topic_keywords):
                    article_rows.append(a)
            else:
                article_rows.append(a)

        # == Fallback: if no articles found in current period, expand time range ==
        fallback_suffix = ""
        report_title_suffix = ""
        if not article_rows:
            from datetime import timedelta as _td
            expanded_start = start_date - _td(days=7)  # Look back up to 7 days
            # Don't go before this month's 1st for weekly+, or before yesterday for daily
            if report_type == "daily":
                max_lookback = start_date - _td(days=3)
            else:
                max_lookback = expanded_start

            if topic_source_ids:
                placeholders = ", ".join(f":s{i}" for i in range(len(topic_source_ids)))
                params = {f"s{i}": sid for i, sid in enumerate(topic_source_ids)}
                params["start_date"] = max_lookback
                params["end_date"] = end_date

                fallback_result = await db.execute(
                    text(f"""
                        SELECT id, title, content, summary, url, published_at, fetched_at
                        FROM raw_articles
                        WHERE source_id IN ({placeholders})
                          AND is_processed = true
                          AND published_at >= :start_date
                          AND published_at <= :end_date
                        ORDER BY published_at DESC
                    """),
                    params,
                )
                all_article_rows = fallback_result.fetchall()

                article_rows = []
                for a in all_article_rows:
                    text_content = f"{a.title or ''} {a.content or ''} {a.summary or ''}".lower()
                    if topic_keywords:
                        if any(kw.lower() in text_content for kw in topic_keywords):
                            article_rows.append(a)
                    else:
                        article_rows.append(a)

                if article_rows:
                    # Update start_date to reflect the fallback range
                    start_date = max_lookback
                    fallback_suffix = "（含回顾）"
                    report_title_suffix = "（含回顾）"
                    import logging as _lg
                    _lg.getLogger(__name__).info(
                        f"[ReportGen] ⚠️ {topic_name} {report_type} 本周期无数据，已回溯至 {max_lookback.date()}，找到 {len(article_rows)} 篇"
                    )
            else:
                fallback_suffix = ""
                report_title_suffix = ""

        # 3. Build article content for AI - concise but informative
        # For very large batches, limit to most recent articles and only titles+summaries
        MAX_AI_ARTICLES = 50
        ai_articles = article_rows[:MAX_AI_ARTICLES]
        total_count = len(article_rows)
        truncated = len(article_rows) > MAX_AI_ARTICLES

        if len(article_rows) > 30:
            articles_json = json.dumps(
                [
                    {
                        "title": a.title,
                        "summary": (a.summary or "")[:200],
                        "content": "",
                        "url": a.url,
                        "published_at": str(a.published_at) if a.published_at else "",
                    }
                    for a in ai_articles
                ],
                ensure_ascii=False,
                indent=2,
            )
        else:
            articles_json = json.dumps(
                [
                    {
                        "title": a.title,
                        "content": (a.content or "")[:500],
                        "summary": (a.summary or "")[:200],
                        "url": a.url,
                        "published_at": str(a.published_at) if a.published_at else "",
                    }
                    for a in ai_articles
                ],
                ensure_ascii=False,
                indent=2,
            )

        type_labels = {"daily": "日", "weekly": "周", "monthly": "月", "quarterly": "季", "yearly": "年"}
        type_label = type_labels.get(report_type, "日")
        type_names = {"daily": "日报", "weekly": "周报", "monthly": "月报", "quarterly": "季报", "yearly": "年报"}
        
        # Smart title based on report type
        import calendar
        iso_week = end_date.isocalendar()
        week_str = f"{end_date.year}年第{iso_week[1]:02d}周"
        month_str = f"{end_date.year}年{end_date.month}月"
        quarter = (end_date.month - 1) // 3 + 1
        quarter_str = f"{end_date.year}年Q{quarter}"
        year_str = f"{end_date.year}年"
        
        time_strs = {"daily": end_date.strftime('%m-%d'), "weekly": week_str, "monthly": month_str,
                     "quarterly": quarter_str, "yearly": year_str}
        time_str = time_strs.get(report_type, end_date.strftime('%Y-%m-%d'))
        report_title = f"{topic_name} - {type_names.get(report_type, '日报')} - {time_str}{report_title_suffix}" 

        if article_rows:
            # 4. Call DeepSeek AI for SWOT analysis
            from app.services.ai import chat_with_deepseek

            # Build prompt based on report type - weekly/monthly get much more comprehensive analysis
            if report_type in ("monthly", "quarterly", "yearly"):
                analysis_depth = "深度战略分析"
                swot_detail = "每项分析200-300字，详细列举具体事件和数据支撑"
                risk_count = "8-12"
                opp_count = "8-12"
                summary_length = "500字以内"
            elif report_type == "weekly":
                analysis_depth = "深度综合分析"
                swot_detail = "每项分析200-300字，详细列举具体事件、趋势数据和因果分析"
                risk_count = "8-12"
                opp_count = "8-12"
                summary_length = "400字以内"
            else:
                analysis_depth = "快速分析"
                swot_detail = "每项分析100-150字"
                risk_count = "3-5"
                opp_count = "3-5"
                summary_length = "200字以内"

            system_prompt = f"""你是一位资深的行业战略分析师，精通{analysis_depth}。你擅长从大量新闻文章中提取关键信息，进行结构化的SWOT分析。

## 你的角色
- 你是专注于「{topic_name}」领域的资深分析专家
- 相关关键词：{', '.join(topic_keywords[:10]) if topic_keywords else '无特定关键词'}
- 你以数据驱动、逻辑严谨的分析风格著称
- 你始终保持客观中立，基于事实而非主观判断

## 分析要求
1. **优势(S)**：从文章内容中提取对「{topic_name}」领域有利的趋势、突破、领先优势
2. **劣势(W)**：识别不足、挑战、落后环节
3. **机会(O)**：发现新的增长点、市场机会、政策利好
4. **威胁(T)**：识别风险、竞争压力、政策风险
5. **风险清单**：列出具体的风险事件，评估等级和影响
6. **机会清单**：列出具体的商业机会，评估潜力和时间窗口

## 输出要求
{swot_detail}
每项SWOT分析必须引用具体文章内容作为依据，对每个论断都要给出数据或事件支撑。
风险清单 {risk_count} 项，每项必须说明风险来源（引用具体新闻事件）。
机会清单 {opp_count} 项，每项必须说明机会来源和实现路径。
整体风险等级评估要合理。
语言通顺、逻辑连贯、数据支撑充分，分析要有因果推理。{type_label}度报告要有趋势分析，不能只是罗列事件。

请始终以JSON格式返回分析结果。"""

            user_prompt = f"""请基于以下 {len(ai_articles)} 篇与「{topic_name}」相关的文章（{type_label}度时间范围），生成一份结构化的{type_label}度战略分析报告。

## 文章列表
{articles_json}

## 输出要求
请严格以以下JSON格式返回分析结果，不要包含任何其他内容，确保分析有深度和广度：

    {{
    "s": "优势分析（{swot_detail}）",
    "w": "劣势分析（{swot_detail}）",
    "o": "机会分析（{swot_detail}）",
    "t": "威胁分析（{swot_detail}）",
    "risks": [
        {{
            "title": "风险名称（30字以内）",
            "description": "风险详细描述（100字以内，说明风险来源和影响机制）",
            "level": "高/中/低",
            "impact": "影响说明（50字以内）"
        }}
    ],
    "opportunities": [
        {{
            "title": "机会名称（30字以内）",
            "description": "机会详细描述（100字以内，说明机会来源和实现路径）",
            "potential": "潜力评估（50字以内）",
            "timeline": "时间窗口（30字以内）"
        }}
    ],
    "risk_level": "整体风险等级：高/中/低",
    "key_trends": "关键趋势总结（{summary_length}，概括本期最重要的3-5个趋势方向）",
    "action_items": [
        "建议1（50字以内）",
        "建议2（50字以内）",
        "建议3（50字以内）"
    ]
}}

请直接返回JSON，不要添加任何解释或说明。确保JSON格式完整、可解析。"""

            # Use higher max_tokens for comprehensive report types
            if report_type in ("monthly", "quarterly", "yearly"):
                ai_max_tokens = 4096
            elif report_type == "weekly":
                ai_max_tokens = 3072
            else:
                ai_max_tokens = 2048

            response = await chat_with_deepseek(system_prompt, [{"role": "user", "content": user_prompt}], max_tokens=ai_max_tokens)

            # Retry loop: up to 3 attempts for empty API response or empty SWOT analysis
            max_retries = 3
            for attempt in range(max_retries):
                # Check if this is an error response (API/request exception or demo mode)
                is_error = response.startswith("（") 
                
                if not is_error:
                    # Try to parse JSON and check if SWOT is non-empty
                    content_raw = response.strip()
                    if content_raw.startswith("```json"):
                        content_raw = content_raw[7:]
                    if content_raw.startswith("```"):
                        content_raw = content_raw[3:]
                    if content_raw.endswith("```"):
                        content_raw = content_raw[:-3]
                    content_raw = content_raw.strip()
                    try:
                        test_data = json.loads(content_raw)
                        has_swot = any(test_data.get(k, "") for k in ["s", "w", "o", "t"])
                        has_risks = len(test_data.get("risks", [])) > 0
                        has_opps = len(test_data.get("opportunities", [])) > 0
                        if has_swot or has_risks or has_opps:
                            break  # Good response, use it
                        logger.warning(f"[ReportGen] AI returned empty analysis (attempt {attempt+1}), retrying...")
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"[ReportGen] AI response parse failed (attempt {attempt+1}): {e}, retrying...")
                        is_error = True
                
                if attempt < max_retries - 1:
                    # Retry with httpx directly and longer timeout
                    import logging as _lg2
                    _lg2.getLogger(__name__).warning(f"[ReportGen] AI retry #{attempt+2} for {topic_name} {report_type}")
                    import httpx as _httpx
                    api_key = __import__('app.core.config', fromlist=['settings']).settings.DEEPSEEK_API_KEY
                    base_url = __import__('app.core.config', fromlist=['settings']).settings.DEEPSEEK_BASE_URL
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": __import__('app.core.config', fromlist=['settings']).settings.DEEPSEEK_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt + "\n\n请务必输出有实质内容的分析，不要返回空字段。如果文章不足，基于已知行业知识补充分析。"},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "temperature": 0.7 + (attempt * 0.1),  # Increase temperature on each retry
                        "max_tokens": ai_max_tokens,
                    }
                    try:
                        async with _httpx.AsyncClient(timeout=180.0) as client:
                            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                            resp.raise_for_status()
                            data_json = resp.json()
                            response = data_json["choices"][0]["message"]["content"]
                    except Exception as retry_err:
                        _lg2.getLogger(__name__).warning(f"[ReportGen] Retry #{attempt+2} failed: {retry_err}")

            # 5. Parse response
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {"s": "", "w": "", "o": "", "t": "", "risks": [], "opportunities": [], "risk_level": "中", "key_trends": "", "action_items": []}

            swot = {"s": data.get("s", ""), "w": data.get("w", ""), "o": data.get("o", ""), "t": data.get("t", "")}
            risk_items = {"risks": data.get("risks", [])}
            opportunities = {"opportunities": data.get("opportunities", [])}
            risk_level = data.get("risk_level", "中")
            key_trends = data.get("key_trends", "")
            action_items = data.get("action_items", [])

            # Guard: if all SWOT fields and risks/opps are empty, mark as draft (AI failed)
            has_substance = any(swot.get(k, "") for k in ["s", "w", "o", "t"]) or \
                           risk_items.get("risks") or \
                           opportunities.get("opportunities")
            if not has_substance:
                status = "draft"
                summary = f"「{topic_name}」{type_label}报生成失败：AI分析未返回有效内容，请稍后重试"
            else:
                status = "generated"

                summary_parts = [f"「{topic_name}」{type_label}报共分析 {len(article_rows)} 篇相关文章（{time_str}）"]
                if fallback_suffix:
                    summary_parts.append(f"（本周期无最新数据，已补充最近{report_type}度数据）")
                if data.get("key_trends"):
                    summary_parts.append(f"趋势：{data['key_trends'][:80]}")
                if data.get("risks"):
                    summary_parts.append(f"识别到 {len(data['risks'])} 项风险")
                if data.get("opportunities"):
                    summary_parts.append(f"发现 {len(data['opportunities'])} 项机会")
                summary = "；".join(summary_parts)
        else:
            swot = {"s": "", "w": "", "o": "", "t": ""}
            risk_items = {"risks": []}
            opportunities = {"opportunities": []}
            risk_level = "中"
            key_trends = ""
            action_items = []
            summary = f"本{type_label}报时间范围内无已处理的文章数据"
            status = "draft"

        now = datetime.utcnow()

        # 6. Build article snapshot with key trends and action items
        source_articles = []
        for a in article_rows:
            source_articles.append({
                "id": str(a.id),
                "title": a.title,
                "summary": (a.summary or "")[:200],
                "url": a.url or "",
                "published_at": str(a.published_at) if a.published_at else "",
                "fetched_at": str(a.fetched_at) if a.fetched_at else "",
            })
        content_snapshot = {
            "articles": source_articles,
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "label": time_str,
            },
            "key_trends": key_trends,
            "action_items": action_items,
        }

        now = datetime.utcnow()

        # 6. Update the existing placeholder report
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
                "title": report_title,
                "summary": summary,
                "content": json.dumps(content_snapshot, ensure_ascii=False) if content_snapshot else None,
                "swot": json.dumps(swot, ensure_ascii=False) if swot else None,
                "risk_level": risk_level,
                "risk_items": json.dumps(risk_items, ensure_ascii=False) if risk_items else None,
                "opportunities": json.dumps(opportunities, ensure_ascii=False) if opportunities else None,
                "push_time": now,
                "status": status,
                "updated_at": now,
            },
        )
        await db.commit()

        # === Auto-push: only push if generation succeeded ===
        if status != "generated":
            logger.info(f"[ReportGen] Skipping push for {report_id}: status is {status} (SWOT empty)")
        else:
            try:
                push_cfg_result = await db.execute(
                    text("""
                        SELECT feishu_chat_id, feishu_push_enabled, webhook_url
                        FROM topic_push_configs
                        WHERE topic_id = :topic_id
                    """),
                    {"topic_id": str(topic_id)},
                )
                push_row = push_cfg_result.fetchone()
                has_webhook = push_row and bool(push_row.webhook_url)
                has_oauth = push_row and push_row.feishu_push_enabled and bool(push_row.feishu_chat_id)

                # Try OAuth-based push
                if has_oauth:
                    from app.services.push_service import push_report_full_with_db
                    push_data = {
                        "feishu_doc_token": None,
                        "report_type": report_type,
                        "title": report_title,
                        "summary": summary,
                        "swot": swot,
                        "risk_level": risk_level,
                        "risk_items": risk_items,
                        "opportunities": opportunities,
                    }
                    await push_report_full_with_db(
                        db=db,
                        report_id=report_id,
                        report_data=push_data,
                        feishu_chat_id=push_row.feishu_chat_id,
                    )

                # Try webhook-based push (fallback or primary)
                if has_webhook:
                    import httpx as _httpx_wh
                    articles = content_snapshot.get("articles", []) if content_snapshot else []
                    article_links = ""
                    for i, art in enumerate(articles[:10], 1):
                        url = art.get("url", "")
                        title_text = (art.get("title", "") or "")[:50]
                        if url:
                            article_links += f"[{i}. {title_text}]({url})\n"
                        else:
                            article_links += f"{i}. {title_text}\n"

                    s_text = (swot.get("s", "") or "")[:300]
                    w_text = (swot.get("w", "") or "")[:300]
                    o_text = (swot.get("o", "") or "")[:300]
                    t_text = (swot.get("t", "") or "")[:300]

                    risk_count = len(risk_items.get("risks", [])) if risk_items else 0
                    opp_count = len(opportunities.get("opportunities", [])) if opportunities else 0

                    level_color_wh = {"高": "red", "中": "yellow", "低": "green"}
                    color_wh = level_color_wh.get(risk_level, "blue")

                    elements_wh = [
                        {"tag": "markdown", "content": f"**📋 摘要**\n{summary[:400]}"},
                        {"tag": "hr"},
                        {"tag": "markdown", "content": f"**💪 优势**\n{s_text}\n\n**⚠️ 劣势**\n{w_text}\n\n**🚀 机会**\n{o_text}\n\n**🔻 威胁**\n{t_text}"},
                        {"tag": "hr"},
                        {"tag": "markdown", "content": f"**整体风险等级：{risk_level}**"},
                    ]

                    if article_links:
                        elements_wh.append({"tag": "hr"})
                        elements_wh.append({"tag": "markdown", "content": f"**📰 源文章快照（{len(articles)}篇）**\n\n{article_links[:1500]}"})

                    card_wh = {
                        "config": {"wide_screen_mode": True},
                        "header": {"title": {"tag": "plain_text", "content": f"📊 {report_title}"}, "template": color_wh},
                        "elements": elements_wh,
                    }
                    wh_payload = {"msg_type": "interactive", "card": card_wh}
                    async with _httpx_wh.AsyncClient(timeout=30.0) as client:
                        wh_resp = await client.post(push_row.webhook_url, json=wh_payload)
                        wh_resp.raise_for_status()
                        wh_result = wh_resp.json()
                        if wh_result.get("code") == 0:
                            logger.info(f"[AutoPush] Webhook push OK for {report_id}")
                        else:
                            logger.warning(f"[AutoPush] Webhook push returned code={wh_result.get('code')}")
            except Exception as e:
                logger.warning(f"Push after report generation failed (non-fatal): {e}")

    except Exception as e:
        logger.error(f"Background report generation failed for {report_id}: {e}")
        # Mark as failed
        now = datetime.utcnow()
        await db.execute(
            text("UPDATE reports SET status = 'failed', updated_at = :updated_at WHERE id = :report_id"),
            {"report_id": str(report_id), "updated_at": now},
        )
        await db.commit()


# ===== Refresh pipeline (one-click RSS collect + match + delete old + generate) =====

async def _run_refresh_pipeline(org_id: UUID, user_id: UUID, db: AsyncSession):
    """
    一键刷新流水线：
    1. 采集所有活跃 RSS 源
    2. 关键词匹配（每个主题）
    3. 删除旧报告
    4. 为每个主题生成 AI 报告
    """
    import json
    import logging
    from datetime import datetime

    logger = logging.getLogger(__name__)
    try:
        now = datetime.utcnow()

        # ---- Step 1: 采集所有活跃 RSS 源 ----
        sources_result = await db.execute(
            text("""
                SELECT id, url
                FROM news_sources
                WHERE source_type = 'rss' AND is_active = TRUE
            """),
        )
        source_rows = sources_result.fetchall()
        logger.info(f"[Refresh] 发现 {len(source_rows)} 个活跃 RSS 源")

        for src in source_rows:
            source_id, url = src
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "No title")
                article_url = entry.get("link") or entry.get("id", "")
                if not article_url:
                    continue

                # Skip duplicates
                existing = await db.execute(
                    text("SELECT id FROM raw_articles WHERE source_id = :source_id AND url = :url"),
                    {"source_id": str(source_id), "url": article_url},
                )
                if existing.fetchone():
                    continue

                # Extract content
                content = None
                if hasattr(entry, "content") and entry.content:
                    content = entry.content[0].value
                elif hasattr(entry, "summary"):
                    content = entry.summary

                # Parse date
                published_at = None
                for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
                    parsed = getattr(entry, date_field, None)
                    if parsed:
                        try:
                            published_at = datetime(*parsed[:6])
                            break
                        except (ValueError, TypeError):
                            continue

                article_id = uuid4()
                await db.execute(
                    text("""
                        INSERT INTO raw_articles (id, source_id, url, title, content, summary,
                                                  published_at, fetched_at, is_processed)
                        VALUES (:id, :source_id, :url, :title, :content, :summary,
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

            # Update source fetch timestamp
            await db.execute(
                text("""
                    UPDATE news_sources
                    SET last_fetch_at = :now, last_fetch_status = 'success'
                    WHERE id = :source_id
                """),
                {"now": now, "source_id": str(source_id)},
            )

        await db.commit()
        logger.info("[Refresh] RSS 采集完成")

        # ---- Step 2: 关键词匹配（每个主题）----
        topics_result = await db.execute(
            text("""
                SELECT id, keywords, exclude_keywords
                FROM topics
                WHERE org_id = :org_id AND is_active = TRUE
            """),
            {"org_id": str(org_id)},
        )
        topic_rows = topics_result.fetchall()
        logger.info(f"[Refresh] 发现 {len(topic_rows)} 个活跃主题")

        from app.services.article_processor import process_unprocessed_articles

        for topic_row in topic_rows:
            topic_id = topic_row.id
            keywords_raw = topic_row.keywords
            exclude_raw = topic_row.exclude_keywords

            keywords = json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
            exclude_keywords = json.loads(exclude_raw) if isinstance(exclude_raw, str) else (exclude_raw or [])

            processed_count = await process_unprocessed_articles(
                db=db,
                topic_id=topic_id,
                keywords=keywords,
                exclude_keywords=exclude_keywords,
            )
            logger.info(f"[Refresh] 主题 {topic_id}: 处理 {processed_count} 篇文章")

        logger.info("[Refresh] 关键词匹配完成")

        # ---- Step 3: 删除该组织下的所有旧报告 ----
        await db.execute(
            text("""
                DELETE FROM reports
                WHERE topic_id IN (SELECT id FROM topics WHERE org_id = :org_id)
            """),
            {"org_id": str(org_id)},
        )
        await db.commit()
        logger.info("[Refresh] 旧报告已删除")

        # ---- Step 4: 为每个主题生成 AI 报告 ----
        for topic_row in topic_rows:
            topic_id = topic_row.id
            report_id = uuid4()

            await db.execute(
                text("""
                    INSERT INTO reports (id, topic_id, report_type, title, summary, content, swot,
                                         risk_level, risk_items, opportunities, push_time,
                                         status, feishu_doc_token, feishu_msg_id,
                                         created_at, updated_at)
                    VALUES (:id, :topic_id, :report_type, :title, :summary, :content, :swot,
                            :risk_level, :risk_items, :opportunities, :push_time,
                            :status, :feishu_doc_token, :feishu_msg_id,
                            :created_at, :updated_at)
                """),
                {
                    "id": str(report_id),
                    "topic_id": str(topic_id),
                    "report_type": "daily",
                    "title": "日度报告 - 生成中...",
                    "summary": None, "content": None, "swot": None,
                    "risk_level": None, "risk_items": None, "opportunities": None,
                    "push_time": None,
                    "status": "pending",
                    "feishu_doc_token": None, "feishu_msg_id": None,
                    "created_at": now, "updated_at": now,
                },
            )
            await db.commit()

            await _run_report_generation(
                report_id=report_id,
                topic_id=topic_id,
                report_type="daily",
                org_id=org_id,
                user_id=user_id,
                db=db,
            )
            logger.info(f"[Refresh] 报告已生成 topic={topic_id} report={report_id}")

        logger.info("[Refresh] 一键刷新流水线完成")

    except Exception as e:
        logger.error(f"[Refresh] 一键刷新失败: {e}", exc_info=True)


# ===== Endpoints =====

@router.get("", response_model=list[ReportResponse])
async def list_reports(
    topic_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List reports for the current user's organization, optionally filtered by topic_id."""
    params = {"org_id": str(current_user.org_id)}
    where_clauses = ["t.org_id = :org_id"]

    if topic_id is not None:
        where_clauses.append("r.topic_id = :topic_id")
        params["topic_id"] = str(topic_id)

    query = text(f"""
        SELECT r.id, r.topic_id, r.report_type, r.title, r.summary,
               r.content, r.swot, r.risk_level, r.risk_items, r.opportunities,
               r.push_time, r.status, r.feishu_doc_token, r.feishu_msg_id,
               r.created_at, r.updated_at
        FROM reports r
        JOIN topics t ON r.topic_id = t.id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY r.created_at DESC
    """)
    result = await db.execute(query, params)
    rows = result.fetchall()
    return [await _row_to_report(row) for row in rows]


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_all_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    一键刷新：采集所有 RSS 源 → 关键词匹配 → 删除旧报告 → 为每个主题生成 AI 报告。

    请求后立即返回 202，后台异步执行完整流水线。
    """
    import asyncio
    from app.core.database import async_session as _async_session

    async def _bg_refresh():
        async with _async_session() as bg_db:
            await _run_refresh_pipeline(
                org_id=current_user.org_id,
                user_id=current_user.id,
                db=bg_db,
            )

    asyncio.create_task(_bg_refresh())

    return {
        "message": "一键刷新已启动，后台正在执行：采集RSS → 关键词匹配 → 删除旧报告 → 生成AI报告",
        "status": "accepted",
    }


@router.post("", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_report(
    report_in: ReportCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new report asynchronously. Returns immediately with a 'pending' report."""
    import asyncio

    # Verify topic belongs to org
    topic_result = await db.execute(
        text("SELECT id, name FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(report_in.topic_id), "org_id": str(current_user.org_id)},
    )
    topic_row = topic_result.fetchone()
    if not topic_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    now = datetime.utcnow()
    type_labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    type_label = type_labels.get(report_in.report_type, "日报")
    placeholder_title = f"{type_label} - 生成中..."

    # Generate report_id ahead of time (SQLite RETURNING may not work reliably)
    from uuid import uuid4 as _uuid4
    report_id = _uuid4()

    await db.execute(
        text("""
            INSERT INTO reports (id, topic_id, report_type, title, summary, content, swot,
                                 risk_level, risk_items, opportunities, push_time,
                                 status, feishu_doc_token, feishu_msg_id,
                                 created_at, updated_at)
            VALUES (:id, :topic_id, :report_type, :title, :summary, :content, :swot,
                    :risk_level, :risk_items, :opportunities, :push_time,
                    :status, :feishu_doc_token, :feishu_msg_id,
                    :created_at, :updated_at)
        """),
        {
            "id": str(report_id),
            "topic_id": str(report_in.topic_id),
            "report_type": report_in.report_type,
            "title": placeholder_title,
            "summary": None,
            "content": None,
            "swot": None,
            "risk_level": None,
            "risk_items": None,
            "opportunities": None,
            "push_time": None,
            "status": "pending",
            "feishu_doc_token": None,
            "feishu_msg_id": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    await db.commit()

    # Build the response manually to avoid reading back from DB
    from pydantic import TypeAdapter
    response_data = {
        "id": report_id,
        "topic_id": report_in.topic_id,
        "report_type": report_in.report_type,
        "title": placeholder_title,
        "summary": None,
        "content": None,
        "swot": None,
        "risk_level": None,
        "risk_items": None,
        "opportunities": None,
        "push_time": None,
        "status": "pending",
        "feishu_doc_token": None,
        "feishu_msg_id": None,
        "created_at": now,
        "updated_at": now,
    }
    resp = TypeAdapter(ReportResponse).validate_python(response_data)

    # Schedule background generation using asyncio.create_task (more reliable than BackgroundTasks for async work)
    from app.core.database import async_session as _async_session

    async def _bg_task():
        async with _async_session() as bg_db:
            await _run_report_generation(
                report_id=report_id,
                topic_id=report_in.topic_id,
                report_type=report_in.report_type,
                org_id=current_user.org_id,
                user_id=current_user.id,
                db=bg_db,
            )

    asyncio.create_task(_bg_task())

    return resp


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single report by ID."""
    result = await db.execute(
        text("""
            SELECT r.id, r.topic_id, r.report_type, r.title, r.summary,
                   r.content, r.swot, r.risk_level, r.risk_items, r.opportunities,
                   r.push_time, r.status, r.feishu_doc_token, r.feishu_msg_id,
                   r.created_at, r.updated_at
            FROM reports r
            JOIN topics t ON r.topic_id = t.id
            WHERE r.id = :report_id AND t.org_id = :org_id
        """),
        {"report_id": str(report_id), "org_id": str(current_user.org_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return await _row_to_report(row)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report."""
    result = await db.execute(
        text("""
            DELETE FROM reports
            WHERE id = :report_id
              AND topic_id IN (SELECT id FROM topics WHERE org_id = :org_id)
        """),
        {"report_id": str(report_id), "org_id": str(current_user.org_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    await db.commit()
