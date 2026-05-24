"""DuckDuckGo 联网搜索服务 - 为智闻·CEO顾问提供行业数据搜索能力"""
import logging
from typing import Optional
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# DuckDuckGo Instant Answer API (免费，无需API Key)
DDG_INSTANT_API = "https://api.duckduckgo.com/"
# DuckDuckGo HTML页面搜索（无API限制）
DDG_HTML_SEARCH = "https://html.duckduckgo.com/html/"


# ===== 连通性探测 =====

_ddg_reachable: bool | None = None
_ddg_check_count: int = 0


async def _check_ddg_reachable() -> bool:
    """探测 DuckDuckGo 是否可访问（3秒快速失败）"""
    global _ddg_reachable, _ddg_check_count
    if _ddg_reachable is not None and _ddg_check_count >= 3:
        return _ddg_reachable
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(DDG_INSTANT_API, params={"q": "test", "format": "json"})
            _ddg_reachable = resp.status_code == 200
    except Exception:
        _ddg_reachable = False
    _ddg_check_count += 1
    return _ddg_reachable


async def search_ddg_instant(query: str, max_results: int = 10) -> list[dict]:
    """
    使用 DuckDuckGo Instant Answer API 搜索。
    适合查询词条、定义、摘要等结构化信息。
    
    Returns:
        list of dicts with keys: Text, FirstURL, Result
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                DDG_INSTANT_API,
                params={
                    "q": query,
                    "format": "json",
                    "no_redirect": 1,
                    "no_html": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        # RelatedTopics 通常包含相关百科信息
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if "Text" in topic:
                results.append({
                    "title": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "source": "duckduckgo",
                })

        # AbstractText 作为摘要
        if data.get("AbstractText"):
            results.insert(0, {
                "title": data.get("Heading", query),
                "content": data.get("AbstractText"),
                "url": data.get("AbstractURL", ""),
                "source": "duckduckgo_abstract",
            })

        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo instant search failed for '{query}': {e}")
        return []


async def search_ddg_html(query: str, max_results: int = 10) -> list[dict]:
    """
    使用 DuckDuckGo HTML 搜索结果页面抓取。
    适合获取新闻、网页搜索结果。
    
    Returns:
        list of dicts with keys: title, url, snippet
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                DDG_HTML_SEARCH,
                params={"q": query},
            )
            resp.raise_for_status()
            html = resp.text

        results = _parse_ddg_html_results(html, max_results)
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo HTML search failed for '{query}': {e}")
        return []


def _parse_ddg_html_results(html: str, max_results: int) -> list[dict]:
    """解析 DuckDuckGo HTML 搜索结果"""
    results = []
    try:
        # DuckDuckGo HTML 结果格式：<a class="result__a" href="URL">Title</a>
        # 每个结果后面跟着 <a class="result__snippet" href="...">Snippet</a>
        import re
        
        # 匹配搜索结果
        pattern = r'<a class="result__a" href="([^"]+)">([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        for url, title in matches[:max_results]:
            title = _clean_html(title)
            results.append({
                "title": title,
                "url": url,
                "source": "duckduckgo_web",
            })
    except Exception as e:
        logger.warning(f"Failed to parse DuckDuckGo HTML results: {e}")
    
    return results


def _clean_html(text: str) -> str:
    """清理HTML实体"""
    import html
    return html.unescape(text).strip()


async def industry_news_search(
    keywords: list[str],
    days_back: int = 7,
    max_results: int = 10,
) -> list[dict]:
    """
    行业新闻搜索：组合多个关键词搜索最近新闻。

    Args:
        keywords: 关键词列表，如 ["人工智能", "行业趋势"]
        days_back: 搜索最近多少天的内容
        max_results: 最大结果数

    Returns:
        list of dicts with title/url/snippet/source
    """
    # 连通性检查：不可达时直接返回空，避免无意义等待
    if not await _check_ddg_reachable():
        return []

    all_results = []
    date_range = f"d{days_back}"  # e.g. "d7" = 最近7天

    for keyword in keywords:
        query = f"{keyword} {date_range}"
        results = await search_ddg_html(query, max_results=max_results // len(keywords))
        all_results.extend(results)

    # 去重（按URL）
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    return unique_results[:max_results]


async def company_research(company_name: str, max_results: int = 5) -> list[dict]:
    """
    公司研究搜索：获取公司相关信息。
    """
    if not await _check_ddg_reachable():
        return []

    results = []
    instant_results = await search_ddg_instant(company_name, max_results=max_results)
    results.extend(instant_results)
    news_results = await search_ddg_html(f"{company_name} 最新动态", max_results=max_results)
    results.extend(news_results)
    return results[:max_results * 2]


async def market_trend_search(
    industry: str,
    max_results: int = 10,
) -> list[dict]:
    """
    市场趋势搜索：搜索行业趋势、报告、数据。
    """
    if not await _check_ddg_reachable():
        return []

    queries = [
        f"{industry} 行业趋势 2024",
        f"{industry} 市场报告",
        f"{industry} 最新动态",
    ]

    all_results = []
    for q in queries:
        results = await search_ddg_html(q, max_results=max_results // len(queries))
        all_results.extend(results)

    # 去重
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    return unique_results[:max_results]


# ===== 供 AI 直接调用的搜索接口 =====

async def quick_search(query: str, max_results: int = 5) -> str:
    """
    快速搜索，返回格式化字符串（供 AI 直接输出）。
    """
    results = await search_ddg_html(query, max_results=max_results)
    if not results:
        return f"未找到与「{query}」相关的搜索结果。"
    
    lines = [f"🔍 搜索「{query}」结果："]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        lines.append(f"   🔗 {r['url']}")
    
    return "\n".join(lines)


async def search_and_summarize(
    query: str,
    max_results: int = 5,
) -> dict:
    """
    搜索并返回结构化结果（供报告生成使用）。
    """
    results = await search_ddg_html(query, max_results=max_results)
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }
