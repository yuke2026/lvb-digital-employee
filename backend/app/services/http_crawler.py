"""HTTP crawler service - fetches articles from web pages via HTTP/HTML scraping"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_source import NewsSource
from app.models.raw_article import RawArticle

# Default headers for HTTP requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _extract_article_from_html(url: str, html: str, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Extract article data from HTML page using BeautifulSoup.
    
    Args:
        url: URL of the article
        html: HTML content
        config: Optional config dict with extraction hints (css selectors, etc.)
    
    Returns:
        Dict with title, content, summary, url, published_at or None
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Title extraction: try config selectors first, then common patterns
    title = None
    title_selectors = config.get("title_selectors", ["h1", "article h1", ".article-title", ".post-title", "title"]) if config else ["h1", "article h1", ".article-title", ".post-title", "title"]
    for selector in title_selectors:
        elem = soup.select_one(selector)
        if elem:
            title = elem.get_text(strip=True)
            break
    if not title:
        title = soup.title.string if soup.title else "No title"
    
    # Content extraction
    content = None
    content_selectors = config.get("content_selectors", ["article", ".article-content", ".post-content", ".entry-content", "main", "#content"]) if config else ["article", ".article-content", ".post-content", ".entry-content", "main", "#content"]
    for selector in content_selectors:
        elem = soup.select_one(selector)
        if elem:
            # Remove script and style elements
            for tag in elem.find_all(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            content = elem.get_text(separator="\n", strip=True)
            break
    
    # Summary extraction (use meta description or first paragraph)
    summary = None
    meta_desc = soup.find("meta", {"name": "description"})
    if meta_desc and meta_desc.get("content"):
        summary = meta_desc["content"]
    else:
        summary_selectors = config.get("summary_selectors", [".article-summary", ".post-summary", ".lead"]) if config else [".article-summary", ".post-summary", ".lead"]
        for selector in summary_selectors:
            elem = soup.select_one(selector)
            if elem:
                summary = elem.get_text(strip=True)
                break
    
    # If no explicit summary, use first ~200 chars of content
    if not summary and content:
        summary = content[:200] + "..." if len(content) > 200 else content
    
    # Published date extraction
    published_at = None
    date_selectors = config.get("date_selectors", ["time", "[itemprop='datePublished']", ".article-date", ".post-date", ".published"]) if config else ["time", "[itemprop='datePublished']", ".article-date", ".post-date", ".published"]
    for selector in date_selectors:
        elem = soup.select_one(selector)
        if elem:
            datetime_str = elem.get("datetime") or elem.get_text(strip=True)
            if datetime_str:
                try:
                    # Try common formats
                    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
                        try:
                            published_at = datetime.strptime(datetime_str[:19] if len(datetime_str) > 19 else datetime_str, fmt)
                            break
                        except ValueError:
                            continue
                except (ValueError, TypeError):
                    pass
            break
    
    # Fallback: meta article:published_time
    if not published_at:
        meta_time = soup.find("meta", {"property": "article:published_time"})
        if meta_time and meta_time.get("content"):
            try:
                published_at = datetime.fromisoformat(meta_time["content"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
    
    return {
        "title": title,
        "content": content,
        "summary": summary,
        "url": url,
        "published_at": published_at,
    }


def _find_article_links(html: str, base_url: str, config: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Find article links from a listing page.
    
    Args:
        html: HTML content of listing page
        base_url: Base URL for resolving relative links
        config: Optional config with link selectors
    
    Returns:
        List of article URLs
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    
    link_selectors = config.get("link_selectors", ["article a", ".article-link", ".post-link", "h2 a", "h3 a"]) if config else ["article a", ".article-link", ".post-link", "h2 a", "h3 a"]
    
    for selector in link_selectors:
        for a_tag in soup.select(selector):
            href = a_tag.get("href")
            if href:
                # Resolve relative URLs
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                links.append(href)
    
    return list(set(links))  # Remove duplicates


async def fetch_http_source(db: AsyncSession, source_id: uuid.UUID) -> int:
    """
    Fetch articles from a news source (source_type='api' or 'crawl') via HTTP.
    
    Uses requests.get() with proper User-Agent headers and BeautifulSoup for HTML parsing.
    For 'api' sources, expects the URL to return structured data (JSON) or HTML article pages.
    For 'crawl' sources, fetches listing pages and extracts article links, then scrapes each.
    
    Args:
        db: Async SQLAlchemy session
        source_id: UUID of the news_source row
    
    Returns:
        Number of articles saved to raw_articles table
    """
    # Fetch the news source
    result = await db.execute(
        select(NewsSource).where(NewsSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise ValueError(f"News source with id {source_id} not found")
    
    if source.source_type not in ("api", "crawl"):
        raise ValueError(f"Source {source_id} is not an HTTP source (type: {source.source_type})")
    
    config = source.config or {}
    articles_saved = 0
    now = datetime.utcnow()
    
    try:
        # Fetch the source URL
        response = requests.get(
            source.url,
            headers=DEFAULT_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        
        content_type = response.headers.get("Content-Type", "")
        
        # Handle JSON response (common for 'api' sources)
        if "application/json" in content_type or source.source_type == "api":
            try:
                data = response.json()
                # Extract URLs from JSON - could be a list or nested
                urls = []
                url_field = config.get("url_field", "url")
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and url_field in item:
                            urls.append(item[url_field])
                elif isinstance(data, dict):
                    items = data.get(config.get("items_field", "articles") or "articles", [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and url_field in item:
                                urls.append(item[url_field])
                
                # Fetch each article URL
                for article_url in urls:
                    try:
                        article_response = requests.get(
                            article_url,
                            headers=DEFAULT_HEADERS,
                            timeout=30,
                        )
                        article_response.raise_for_status()
                        
                        article_data = _extract_article_from_html(
                            article_url,
                            article_response.text,
                            config
                        )
                        
                        if article_data and article_data.get("url"):
                            saved = await _save_article(db, source_id, article_data, now)
                            articles_saved += saved
                    except requests.RequestException:
                        continue
                        
            except (ValueError, requests.RequestException):
                # Fall back to treating as HTML
                pass
        
        # Handle HTML response
        if "text/html" in content_type or not articles_saved:
            html = response.text
            
            # For 'crawl' type, find article links on listing page
            if source.source_type == "crawl":
                article_links = _find_article_links(html, source.url, config)
                
                for article_url in article_links:
                    try:
                        article_response = requests.get(
                            article_url,
                            headers=DEFAULT_HEADERS,
                            timeout=30,
                        )
                        article_response.raise_for_status()
                        
                        article_data = _extract_article_from_html(
                            article_url,
                            article_response.text,
                            config
                        )
                        
                        if article_data and article_data.get("url"):
                            saved = await _save_article(db, source_id, article_data, now)
                            articles_saved += saved
                    except requests.RequestException:
                        continue
            else:
                # For 'api' type when no JSON detected, treat as single article page
                article_data = _extract_article_from_html(source.url, html, config)
                if article_data and article_data.get("url"):
                    saved = await _save_article(db, source_id, article_data, now)
                    articles_saved += saved
        
        source.last_fetch_at = now
        source.last_fetch_status = "success" if articles_saved > 0 else "no_new_articles"
        
    except requests.RequestException as e:
        source.last_fetch_at = now
        source.last_fetch_status = f"error: {str(e)}"
    
    await db.commit()
    return articles_saved


async def _save_article(
    db: AsyncSession,
    source_id: uuid.UUID,
    article_data: Dict[str, Any],
    now: datetime
) -> int:
    """
    Save an article to raw_articles table if URL doesn't already exist.
    
    Returns:
        1 if article was saved, 0 if duplicate
    """
    url = article_data.get("url")
    if not url:
        return 0
    
    # Check for duplicate URL
    existing = await db.execute(
        select(RawArticle).where(
            RawArticle.source_id == source_id,
            RawArticle.url == url
        )
    )
    if existing.scalar_one_or_none():
        return 0
    
    article = RawArticle(
        source_id=source_id,
        title=article_data.get("title", "No title"),
        content=article_data.get("content"),
        summary=article_data.get("summary"),
        url=url,
        published_at=article_data.get("published_at"),
        fetched_at=now,
        is_processed=False
    )
    db.add(article)
    return 1
