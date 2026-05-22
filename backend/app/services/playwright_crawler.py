"""Playwright-based crawler for JavaScript-rendered pages."""
import uuid
import subprocess
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_source import NewsSource
from app.models.raw_article import RawArticle


def _ensure_playwright_installed():
    """Ensure Playwright is installed, install if not."""
    try:
        import playwright
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        import playwright  # noqa: F401


async def _extract_articles_from_page(page) -> list[dict]:
    """
    Extract articles from a rendered page.
    
    Looks for common article patterns: <article> tags, list items with links,
    or structured div elements commonly used by news sites.
    """
    articles = []
    
    # Try to find article elements
    article_elements = await page.query_selector_all("article")
    
    for elem in article_elements:
        title_elem = await elem.query_selector("h1, h2, h3, a")
        link_elem = await elem.query_selector("a[href]")
        content_elem = await elem.query_selector("p")
        date_elem = await elem.query_selector("time, [datetime], .date, .published")
        
        title = None
        url = None
        content = None
        published_at = None
        
        if title_elem:
            title = await title_elem.inner_text()
        
        if link_elem:
            url = await link_elem.get_attribute("href")
        
        if content_elem:
            content = await content_elem.inner_text()
        
        if date_elem:
            datetime_attr = await date_elem.get_attribute("datetime")
            if datetime_attr:
                try:
                    published_at = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
        
        if title and url:
            articles.append({
                "title": title.strip(),
                "url": url.strip(),
                "content": content.strip() if content else None,
                "published_at": published_at
            })
    
    # Fallback: find all links on the page and try to extract article info
    if not articles:
        link_elements = await page.query_selector_all("a[href]")
        
        for link in link_elements:
            href = await link.get_attribute("href")
            if not href or not href.startswith("http"):
                continue
            
            # Try to get parent article context
            parent = await link.query_selector("xpath=ancestor::article")
            if not parent:
                parent = await link.query_selector("xpath=ancestor::li")
                if not parent:
                    parent = await link.query_selector("xpath=ancestor::div[contains(@class, 'article') or contains(@class, 'post') or contains(@class, 'item')]")
            
            if parent:
                title = await link.inner_text()
                if title and len(title) > 10:  # Likely an article title
                    articles.append({
                        "title": title.strip(),
                        "url": href.strip(),
                        "content": None,
                        "published_at": None
                    })
    
    return articles


async def fetch_playwright_source(db: AsyncSession, source_id: uuid.UUID) -> int:
    """
    Fetch articles from a JavaScript-rendered page using Playwright.
    
    Args:
        db: Async SQLAlchemy session
        source_id: UUID of the news_source row (url, source_type='crawl')
    
    Returns:
        Number of articles saved to raw_articles table
    """
    # Ensure playwright is installed
    _ensure_playwright_installed()
    
    import playwright.async_api as pw
    
    # Fetch the news source
    result = await db.execute(
        select(NewsSource).where(NewsSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise ValueError(f"News source with id {source_id} not found")
    
    if source.source_type != "crawl":
        raise ValueError(f"Source {source_id} is not a crawl source (type: {source.source_type})")
    
    now = datetime.utcnow()
    articles_saved = 0
    
    async with pw.async_playwright() as p:
        # Launch chromium in headless mode
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to the source URL
            await page.goto(source.url, wait_until="networkidle", timeout=30000)
            
            # Wait for content to render
            await page.wait_for_selector("article, a[href]", timeout=10000)
            
            # Extract articles from the rendered page
            articles = await _extract_articles_from_page(page)
            
            for article_data in articles:
                url = article_data["url"]
                
                # Skip URLs without valid content
                if not url or not url.startswith("http"):
                    continue
                
                # Check for duplicate URL in raw_articles for this source
                existing = await db.execute(
                    select(RawArticle).where(
                        RawArticle.source_id == source_id,
                        RawArticle.url == url
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                
                # Create new raw article
                article = RawArticle(
                    source_id=source_id,
                    title=article_data["title"],
                    content=article_data.get("content"),
                    summary=None,
                    url=url,
                    published_at=article_data.get("published_at"),
                    fetched_at=now,
                    is_processed=False
                )
                db.add(article)
                articles_saved += 1
            
        finally:
            await browser.close()
    
    # Update source last_fetch_at and status
    source.last_fetch_at = now
    source.last_fetch_status = "success" if articles_saved > 0 else "no_new_articles"
    
    await db.commit()
    return articles_saved
