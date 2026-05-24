"""智闻·CEO顾问 API - 行业情报搜索、报告生成、定时任务管理"""
from uuid import UUID
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.ceo_advisor import (
    search_industry_intelligence,
    research_company,
    analyze_market_trend,
    generate_ceo_digest_report,
    push_report_to_feishu,
)

router = APIRouter(prefix="/ceo-advisor", tags=["CEO顾问"])


# ===== Schemas =====

class IndustrySearchRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, max_length=10)
    days_back: int = Field(default=7, ge=1, le=90)


class CompanyResearchRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=100)


class MarketTrendRequest(BaseModel):
    industry: str = Field(..., min_length=1, max_length=100)


class CEOReportGenerateRequest(BaseModel):
    topic_id: UUID
    keywords: list[str] = Field(..., min_length=1, max_length=10)
    report_type: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")


class WebhookPushRequest(BaseModel):
    report_data: dict
    feishu_webhook_url: str


class CEOIntelligenceResponse(BaseModel):
    query: str
    count: int
    ai_summary: str
    search_time: str
    results: list


# ===== Endpoints =====

@router.post("/search/industry", response_model=CEOIntelligenceResponse)
async def api_search_industry(
    req: IndustrySearchRequest,
    current_user: User = Depends(get_current_user),
):
    """搜索行业情报（支持多关键词）"""
    result = await search_industry_intelligence(
        keywords=req.keywords,
        days_back=req.days_back,
    )
    return CEOIntelligenceResponse(
        query=str(req.keywords),
        count=result.get("count", 0),
        ai_summary=result.get("ai_summary", ""),
        search_time=result.get("search_time", ""),
        results=result.get("results", []),
    )


@router.post("/research/company")
async def api_research_company(
    req: CompanyResearchRequest,
    current_user: User = Depends(get_current_user),
):
    """研究目标公司信息"""
    result = await research_company(company_name=req.company_name)
    return {
        "company": result.get("company"),
        "count": result.get("count", 0),
        "ai_summary": result.get("ai_summary", ""),
        "research_time": result.get("research_time"),
        "results": result.get("results", []),
    }


@router.post("/analyze/trend")
async def api_analyze_trend(
    req: MarketTrendRequest,
    current_user: User = Depends(get_current_user),
):
    """分析市场趋势"""
    result = await analyze_market_trend(industry=req.industry)
    return {
        "industry": result.get("industry"),
        "count": result.get("count", 0),
        "ai_summary": result.get("ai_summary", ""),
        "analysis_time": result.get("analysis_time"),
        "results": result.get("results", []),
    }


@router.post("/report/generate")
async def api_generate_ceo_report(
    req: CEOReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    为CEO顾问生成行业洞察报告。
    
    1. 联网搜索最新行业数据
    2. AI分析生成洞察
    3. 保存到 reports 表
    4. 自动推送（如配置了 webhook）
    """
    # Verify topic belongs to org
    from sqlalchemy import text
    topic_result = await db.execute(
        text("SELECT id FROM topics WHERE id = :topic_id AND org_id = :org_id"),
        {"topic_id": str(req.topic_id), "org_id": str(current_user.org_id)},
    )
    if not topic_result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    # Generate CEO report
    report_data = await generate_ceo_digest_report(
        topic_id=req.topic_id,
        org_id=current_user.org_id,
        user_id=current_user.id,
        keywords=req.keywords,
        report_type=req.report_type,
    )

    # Save to DB
    now = datetime.utcnow()
    result = await db.execute(
        text("""
            INSERT INTO reports (topic_id, report_type, title, summary, content,
                                 swot, risk_level, risk_items, opportunities,
                                 push_time, status, created_at, updated_at)
            VALUES (:topic_id, :report_type, :title, :summary, :content,
                    :swot, :risk_level, :risk_items, :opportunities,
                    :push_time, :status, :created_at, :updated_at)
            RETURNING id
        """),
        {
            "topic_id": str(req.topic_id),
            "report_type": req.report_type,
            "title": report_data.get("title", ""),
            "summary": report_data.get("summary"),
            "content": report_data.get("content"),
            "swot": report_data.get("swot"),
            "risk_level": report_data.get("risk_level"),
            "risk_items": report_data.get("risk_items"),
            "opportunities": report_data.get("opportunities"),
            "push_time": report_data.get("push_time"),
            "status": report_data.get("status", "generated"),
            "created_at": now,
            "updated_at": now,
        },
    )
    await db.commit()
    row = result.fetchone()
    report_id = row[0] if row else None

    # Push via webhook if configured
    push_cfg_result = await db.execute(
        text("SELECT feishu_chat_id, feishu_push_enabled, webhook_url FROM topic_push_configs WHERE topic_id = :topic_id"),
        {"topic_id": str(req.topic_id)},
    )
    push_row = push_cfg_result.fetchone()

    push_result = None
    if push_row and push_row.webhook_url:
        push_result = await push_report_to_feishu(report_data, push_row.webhook_url)

    return {
        "report_id": str(report_id) if report_id else None,
        "title": report_data.get("title"),
        "summary": report_data.get("summary"),
        "risk_level": report_data.get("risk_level"),
        "push_result": push_result,
    }


@router.post("/push/webhook")
async def api_push_webhook(
    req: WebhookPushRequest,
    current_user: User = Depends(get_current_user),
):
    """
    直接通过飞书 Webhook 推送报告卡片消息。
    无需飞书应用权限，只需一个机器人 Webhook URL。
    """
    result = await push_report_to_feishu(
        report_data=req.report_data,
        feishu_webhook_url=req.feishu_webhook_url,
    )
    return result
