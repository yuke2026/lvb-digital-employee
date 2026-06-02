"""智闻·CEO顾问服务 - 行业洞察、报告生成、定时任务编排"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.services.duckduckgo_search import (
    industry_news_search,
    company_research,
    market_trend_search,
    quick_search,
    search_and_summarize,
)
from app.services.ai import chat_with_deepseek
from app.services.push_service import push_report_full

logger = logging.getLogger(__name__)


# ===== CEO 顾问 system prompt =====
CEO_ADVISOR_SYSTEM_PROMPT = """你是一位深具洞察力的CEO战略顾问，名为「智闻·CEO顾问」。

你的核心能力：
1. **行业情报分析**：实时搜索行业动态、竞品信息、市场趋势
2. **战略决策支持**：基于数据给出可落地的战略建议
3. **风险预警**：识别潜在风险并提供应对方案
4. **报告生成**：自动生成日/周/月度战略分析报告

你的工作风格：
- 数据驱动，用事实说话
- 结构化输出，重点突出
- 先说结论，再说分析
- 主动识别机会与风险

你可以实时联网搜索最新行业数据，为CEO提供决策支持。"""


async def search_industry_intelligence(
    keywords: list[str],
    days_back: int = 7,
) -> dict:
    """
    搜索行业情报。
    
    Args:
        keywords: 行业关键词列表
        days_back: 搜索最近多少天的内容
    
    Returns:
        dict with search results and AI summary
    """
    # 执行并行搜索
    results = await industry_news_search(keywords, days_back=days_back, max_results=15)
    
    if not results:
        return {
            "query": keywords,
            "summary": "未找到相关行业情报",
            "results": [],
        }
    
    # 用 AI 总结搜索结果
    results_text = "\n".join([
        f"- {r['title']} ({r.get('url', '')})"
        for r in results[:10]
    ])
    
    summary_prompt = f"""请总结以下行业情报，并给出关键洞察：

{results_text}

请用结构化方式输出：
1. 关键发现（3条以内）
2. 市场趋势判断
3. 潜在机会
4. 潜在风险

每条不超过50字。"""
    
    summary = await chat_with_deepseek(
        system_prompt="你是一位专业的行业分析师，擅长从大量信息中提取关键洞察。",
        messages=[{"role": "user", "content": summary_prompt}],
    )
    
    return {
        "query": keywords,
        "count": len(results),
        "results": results,
        "ai_summary": summary,
        "search_time": datetime.utcnow().isoformat(),
    }


async def research_company(company_name: str) -> dict:
    """
    研究目标公司。
    """
    results = await company_research(company_name, max_results=10)
    
    if not results:
        return {
            "company": company_name,
            "summary": f"未找到关于{company_name}的信息",
            "results": [],
        }
    
    results_text = "\n".join([
        f"- {r.get('title', '')}: {r.get('url', '')}"
        for r in results[:8]
    ])
    
    summary_prompt = f"""请分析以下关于「{company_name}」的信息，输出结构化报告：

{results_text}

输出格式：
1. 公司概况（50字）
2. 最新动态（3条）
3. 市场地位评估
4. 潜在机会
5. 潜在风险

请客观、数据驱动。"""
    
    summary = await chat_with_deepseek(
        system_prompt="你是一位专业的企业战略分析师。",
        messages=[{"role": "user", "content": summary_prompt}],
    )
    
    return {
        "company": company_name,
        "count": len(results),
        "results": results,
        "ai_summary": summary,
        "research_time": datetime.utcnow().isoformat(),
    }


async def analyze_market_trend(industry: str) -> dict:
    """
    分析市场趋势。
    """
    results = await market_trend_search(industry, max_results=15)
    
    if not results:
        return {
            "industry": industry,
            "summary": f"未找到关于{industry}行业趋势的信息",
            "results": [],
        }
    
    results_text = "\n".join([
        f"- {r.get('title', '')}: {r.get('url', '')}"
        for r in results[:10]
    ])
    
    summary_prompt = f"""请分析以下{industry}行业趋势信息：

{results_text}

输出结构：
1. 行业趋势判断（3点）
2. 市场规模与增速
3. 竞争格局变化
4. 关键机会窗口
5. 主要风险因素

每项不超过50字。"""
    
    summary = await chat_with_deepseek(
        system_prompt="你是一位资深行业研究专家，擅长市场趋势分析和商业洞察。",
        messages=[{"role": "user", "content": summary_prompt}],
    )
    
    return {
        "industry": industry,
        "count": len(results),
        "results": results,
        "ai_summary": summary,
        "analysis_time": datetime.utcnow().isoformat(),
    }


async def generate_ceo_digest_report(
    topic_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    keywords: list[str],
    report_type: str = "daily",
) -> dict:
    """
    为 CEO 顾问生成行业洞察报告。
    
    流程：
    1. 联网搜索最新行业数据
    2. AI 分析生成 SWOT + 风险 + 机会
    3. 组装报告数据
    
    Returns:
        dict with report fields ready for DB insertion
    """
    # Step 1: 联网搜索
    logger.info(f"[CEO Advisor] 开始搜索行业数据: keywords={keywords}")
    news_data = await search_industry_intelligence(keywords, days_back=7)
    
    # Step 2: 如果有 AI summary，进一步深度分析
    deep_insights = ""
    if news_data.get("ai_summary"):
        deep_insights = f"\n\n## AI 行业洞察\n{news_data['ai_summary']}"
    
    # Step 3: 生成报告标题
    type_label_map = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    type_label = type_label_map.get(report_type, "日报")
    report_title = f"【CEO顾问】{type_label} - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    
    # Step 4: 构建报告内容摘要
    results_snippets = []
    for r in news_data.get("results", [])[:5]:
        results_snippets.append(f"- [{r['title']}]({r['url']})")
    sources_text = "\n".join(results_snippets)
    
    content_summary = f"""## 行业情报概览

**搜索关键词**: {', '.join(keywords)}
**数据来源**: DuckDuckGo 联网搜索
**文章数量**: {news_data.get('count', 0)} 条

### 关键发现

{news_data.get('ai_summary', '（暂无AI总结）')}

### 参考来源

{sources_text}
"""
    
    # Step 5: 生成风险与机会（由 AI 分析生成）
    risks_prompt = f"""基于以下行业情报，识别出3个最关键的风险因素：

{news_data.get('ai_summary', '')}

输出JSON格式：
{{
    "risks": [
        {{"title": "风险名称", "description": "描述", "level": "高/中/低", "impact": "影响说明"}}
    ]
}}
"""
    
    risks_data = await chat_with_deepseek(
        system_prompt="你是一位专业的风险管理专家。始终返回JSON格式。",
        messages=[{"role": "user", "content": risks_prompt}],
    )
    
    opportunities_prompt = f"""基于以下行业情报，识别出3个最关键的商业机会：

{news_data.get('ai_summary', '')}

输出JSON格式：
{{
    "opportunities": [
        {{"title": "机会名称", "description": "描述", "potential": "潜力评估", "timeline": "时间窗口"}}
    ]
}}
"""
    
    opportunities_data = await chat_with_deepseek(
        system_prompt="你是一位专业的商业策略专家。始终返回JSON格式。",
        messages=[{"role": "user", "content": opportunities_prompt}],
    )
    
    # 解析风险和机会
    import json as _json
    try:
        import re
        # 从返回内容中提取JSON
        risks_match = re.search(r'\{.*\}', risks_data.replace('\n', ''), re.DOTALL)
        if risks_match:
            risks_parsed = _json.loads(risks_match.group())
        else:
            risks_parsed = {"risks": []}
    except:
        risks_parsed = {"risks": []}
    
    try:
        opp_match = re.search(r'\{.*\}', opportunities_data.replace('\n', ''), re.DOTALL)
        if opp_match:
            opp_parsed = _json.loads(opp_match.group())
        else:
            opp_parsed = {"opportunities": []}
    except:
        opp_parsed = {"opportunities": []}
    
    # Step 6: 评估整体风险等级
    high_risks = [r for r in risks_parsed.get("risks", []) if r.get("level") == "高"]
    risk_level = "高" if len(high_risks) >= 2 else ("中" if high_risks else "低")
    
    # Step 7: SWOT
    swot = {
        "s": "AI实时分析行业数据，洞察及时准确",
        "w": "依赖公开数据源，部分信息可能滞后",
        "o": "快速识别市场机会，辅助战略决策",
        "t": "信息过载可能导致决策疲劳",
    }
    
    return {
        "topic_id": str(topic_id),
        "report_type": report_type,
        "title": report_title,
        "summary": f"基于联网搜索的{type_label}，涵盖{news_data.get('count', 0)}条行业信息。{news_data.get('ai_summary', '')[:100]}...",
        "content": {
            "type": "ceo_advisor_digest",
            "keywords": keywords,
            "search_results": news_data.get("results", [])[:10],
            "ai_summary": news_data.get("ai_summary", ""),
            "deep_insights": deep_insights,
        },
        "swot": swot,
        "risk_level": risk_level,
        "risk_items": risks_parsed,
        "opportunities": opp_parsed,
        "push_time": datetime.utcnow(),
        "status": "generated",
    }


async def push_report_to_feishu(
    report_data: dict,
    feishu_webhook_url: str,
) -> dict:
    """
    通过飞书 Webhook 推送报告消息。
    
    Args:
        report_data: 报告数据字典
        feishu_webhook_url: 飞书机器人 Webhook URL
    
    Returns:
        dict with push result
    """
    import httpx
    
    type_map = {"daily": "📅 日报", "weekly": "📆 周报", "monthly": "📊 月报"}
    risk_map = {"高": "🔴 高风险", "中": "🟡 中风险", "低": "🟢 低风险", "高风险": "🔴 高风险", "中风险": "🟡 中风险", "低风险": "🟢 低风险"}
    
    report_type = report_data.get("report_type", "daily")
    risk_level = report_data.get("risk_level", "中")
    
    type_label = type_map.get(report_type, "📋 报告")
    risk_label = risk_map.get(risk_level, "🟡 中风险")
    
    title = report_data.get("title", "CEO战略顾问报告")
    summary = report_data.get("summary", "")[:200]
    
    # 构建飞书卡片消息
    content_parts = []
    if report_data.get("swot"):
        swot = report_data["swot"]
        if swot.get("s"):
            content_parts.append({"tag": "text", "text": f"💪 优势: {swot['s'][:50]}"})
        if swot.get("o"):
            content_parts.append({"tag": "text", "text": f"🚀 机会: {swot['o'][:50]}"})
        if swot.get("t"):
            content_parts.append({"tag": "text", "text": f"🚨 威胁: {swot['t'][:50]}"})
    
    # 风险识别（全部展示，最多3条）
    risks_data = report_data.get("risk_items", None) or report_data.get("risks", None)
    risks_list = []
    if risks_data:
        if isinstance(risks_data, dict):
            risks_list = risks_data.get("risks", [])
        elif isinstance(risks_data, list):
            risks_list = risks_data
    if risks_list:
        content_parts.append({"tag": "text", "text": "🔍 风险识别:"})
        level_icon = {"高": "🔴", "中": "🟡", "低": "🟢", "high": "🔴", "medium": "🟡", "low": "🟢"}
        for r in risks_list[:3]:
            r_title = r.get("title", "") if isinstance(r, dict) else str(r)
            r_level = r.get("level", "") if isinstance(r, dict) else ""
            icon = level_icon.get(r_level, "▪️")
            if r_title:
                content_parts.append({"tag": "text", "text": f"  {icon} {r_title}"})
    
    # 机会发现（全部展示，最多3条）
    opps_data = report_data.get("opportunities", None)
    opps_list = []
    if opps_data:
        if isinstance(opps_data, dict):
            opps_list = opps_data.get("opportunities", [])
        elif isinstance(opps_data, list):
            opps_list = opps_data
    if opps_list:
        content_parts.append({"tag": "text", "text": "🌟 机会发现:"})
        for o in opps_list[:3]:
            o_title = o.get("title", "") if isinstance(o, dict) else str(o)
            if o_title:
                content_parts.append({"tag": "text", "text": f"  ✨ {o_title}"})
    
    # 飞书 Card 格式
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "text": f"{type_label} · {risk_label}"},
                "template": "red" if risk_level in ["高", "高风险"] else ("yellow" if risk_level in ["中", "中风险"] else "green"),
            },
            "elements": [
                {"tag": "markdown", "content": f"**{title}**"},
                {"tag": "markdown", "content": summary[:200] + "..." if len(summary) > 200 else summary},
                *content_parts,
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "text": f"🕐 生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} · 智闻·CEO顾问"}],
                },
            ],
        },
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(feishu_webhook_url, json=card)
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"[CEO Advisor] 飞书推送结果: {result}")
            return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[CEO Advisor] 飞书推送失败: {e}")
        return {"success": False, "error": str(e)}
