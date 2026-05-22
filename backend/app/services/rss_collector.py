"""RSS collector service - fetches articles from RSS feeds and saves to raw_articles table"""
import uuid
from datetime import datetime
from typing import Optional

import feedparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_source import NewsSource
from app.models.raw_article import RawArticle


def _parse_feed_entry_date(entry) -> Optional[datetime]:
    """Parse date from feed entry, handling multiple formats"""
    date_fields = ["published_parsed", "updated_parsed", "created_parsed"]
    for field in date_fields:
        if hasattr(entry, field):
            parsed = getattr(entry, field)
            if parsed:
                try:
                    return datetime(*parsed[:6])
                except (ValueError, TypeError):
                    continue
    return None


def _extract_content(entry) -> Optional[str]:
    """Extract content from feed entry"""
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].value if entry.content else None
    if hasattr(entry, "summary_detail") and entry.summary_detail:
        return entry.summary_detail.value
    if hasattr(entry, "summary"):
        return entry.summary
    return None


def _extract_title(entry) -> str:
    """Extract title from feed entry"""
    if hasattr(entry, "title"):
        return entry.title
    return "No title"


def _extract_url(entry) -> str:
    """Extract URL from feed entry"""
    if hasattr(entry, "link"):
        return entry.link
    if hasattr(entry, "id"):
        return entry.id
    return ""


async def fetch_rss_source(db: AsyncSession, source_id: uuid.UUID) -> int:
    """
    Fetch articles from an RSS source and save to raw_articles table.
    
    Args:
        db: Async SQLAlchemy session
        source_id: UUID of the news_source row (url, source_type='rss')
    
    Returns:
        Number of articles saved to raw_articles table
    """
    result = await db.execute(
        select(NewsSource).where(NewsSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise ValueError(f"News source with id {source_id} not found")
    
    if source.source_type != "rss":
        raise ValueError(f"Source {source_id} is not an RSS source (type: {source.source_type})")
    
    feed = feedparser.parse(source.url)
    
    articles_saved = 0
    now = datetime.utcnow()
    
    for entry in feed.entries:
        title = _extract_title(entry)
        url = _extract_url(entry)
        content = _extract_content(entry)
        summary = getattr(entry, "summary", None) if not content else None
        published_at = _parse_feed_entry_date(entry)
        
        if not url:
            continue
        
        existing = await db.execute(
            select(RawArticle).where(
                RawArticle.source_id == source_id,
                RawArticle.url == url
            )
        )
        if existing.scalar_one_or_none():
            continue
        
        article = RawArticle(
            source_id=source_id,
            title=title,
            content=content,
            summary=summary,
            url=url,
            published_at=published_at,
            fetched_at=now,
            is_processed=False
        )
        db.add(article)
        articles_saved += 1
    
    source.last_fetch_at = now
    source.last_fetch_status = "success" if articles_saved > 0 else "no_new_articles"
    
    await db.commit()
    return articles_saved
