from uuid import UUID
from datetime import datetime
import json, logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["报告推送"])


@router.post("/api/v1/reports/{report_id}/push")
async def manual_push_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动推送指定报告到飞书 (webhook + OAuth)"""
    # 1. Load report
    report_row = await db.execute(
        text("SELECT id, topic_id, title, report_type, summary, swot, risk_level, risk_items, opportunities, content, status FROM reports WHERE id = :id"),
        {"id": str(report_id)},
    )
    report = report_row.fetchone()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    if report.status != "generated":
        raise HTTPException(status_code=400, detail=f"报告状态为 {report.status}，不能推送")

    # Parse JSON fields
    def _j(v):
        if v is None: return None
        if isinstance(v, str):
            try: return json.loads(v)
            except: return v
        return v

    swot = _j(report.swot) or {}
    risk_items = _j(report.risk_items) or {}
    opportunities = _j(report.opportunities) or {}
    content_snapshot = _j(report.content) or {}

    # 2. Load topic push config
    push_row = await db.execute(
        text("SELECT feishu_chat_id, feishu_push_enabled, webhook_url FROM topic_push_configs WHERE topic_id = :topic_id"),
        {"topic_id": str(report.topic_id)},
    )
    push_cfg = push_row.fetchone()

    results = {"webhook": False, "oauth": False, "errors": []}

    # 3. Push via webhook
    if push_cfg and push_cfg.webhook_url:
        try:
            articles = content_snapshot.get("articles", []) if content_snapshot else []
            article_links = ""
            for i, art in enumerate(articles[:10], 1):
                url = art.get("url", "")
                title_text = (art.get("title", "") or "")[:50]
                article_links += f"[{i}. {title_text}]({url})\n" if url else f"{i}. {title_text}\n"

            s_text = (swot.get("s", "") or "")[:300]
            w_text = (swot.get("w", "") or "")[:300]
            o_text = (swot.get("o", "") or "")[:300]
            t_text = (swot.get("t", "") or "")[:300]

            level_color = {"高": "red", "中": "yellow", "低": "green"}
            color = level_color.get(report.risk_level or "中", "blue")

            elements = [
                {"tag": "markdown", "content": f"**📋 摘要**\n{(report.summary or '')[:400]}"},
                {"tag": "hr"},
                {"tag": "markdown", "content": f"**💪 优势**\n{s_text}\n\n**⚠️ 劣势**\n{w_text}\n\n**🚀 机会**\n{o_text}\n\n**🔻 威胁**\n{t_text}"},
                {"tag": "hr"},
                {"tag": "markdown", "content": f"**整体风险等级：{report.risk_level or '中'}**"},
            ]
            if article_links:
                elements.append({"tag": "hr"})
                elements.append({"tag": "markdown", "content": f"**📰 源文章快照（{len(articles)}篇）**\n\n{article_links[:1500]}"})

            card = {
                "config": {"wide_screen_mode": True},
                "header": {"title": {"tag": "plain_text", "content": f"📊 {report.title}"}, "template": color},
                "elements": elements,
            }
            payload = {"msg_type": "interactive", "card": card}

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(push_cfg.webhook_url, json=payload)
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") == 0:
                    results["webhook"] = True
                    logger.info(f"[ManualPush] Webhook OK for {report_id}")
                else:
                    results["errors"].append(f"Webhook返回code={result.get('code')}")
        except Exception as e:
            results["errors"].append(f"Webhook推送失败: {e}")

    # 4. Push via OAuth
    if push_cfg and push_cfg.feishu_push_enabled and push_cfg.feishu_chat_id:
        try:
            from app.services.push_service import push_report_full_with_db
            push_data = {
                "feishu_doc_token": None,
                "report_type": report.report_type,
                "title": report.title,
                "summary": report.summary,
                "swot": swot,
                "risk_level": report.risk_level,
                "risk_items": risk_items,
                "opportunities": opportunities,
            }
            oauth_result = await push_report_full_with_db(
                db=db,
                report_id=report_id,
                report_data=push_data,
                feishu_chat_id=push_cfg.feishu_chat_id,
            )
            results["oauth"] = True
        except Exception as e:
            results["errors"].append(f"OAuth推送失败: {e}")

    if not results["webhook"] and not results["oauth"]:
        raise HTTPException(status_code=500, detail=f"推送失败: {'; '.join(results['errors'])}")

    return {"success": True, "webhook": results["webhook"], "oauth": results["oauth"], "errors": results["errors"]}
