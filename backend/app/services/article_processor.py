"""Article processing service - embedding, dedup, and summary generation."""
import hashlib
import uuid
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedder import get_embedding
from app.services.ai import chat_with_deepseek


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Remove common tracking parameters and trailing slashes."""
    url = url.strip().lower()
    # Remove trailing slash
    url = url.rstrip("/")
    # Remove utm_* parameters
    url = re.sub(r"[?&]utm_[^=]*=[^&]*", "", url)
    return url


def _url_fingerprint(url: str) -> str:
    """Fast hash-based fingerprint of a normalized URL."""
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()[:16]


def _title_fingerprint(title: str, max_words: int = 10) -> str:
    """
    Hash-based fingerprint of a normalized title.
    Uses first N words to catch slight variations.
    """
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    words = normalized.split()
    core = " ".join(words[:max_words])
    return hashlib.sha256(core.encode()).hexdigest()[:16]


def _keyword_filter(
    title: str,
    content: Optional[str],
    keywords: list[str],
    exclude_keywords: list[str],
) -> bool:
    """
    Return True if article passes keyword / exclude_keyword filters.
    At least one keyword must match (if keywords is non-empty).
    No exclude_keyword may appear in title or content.
    """
    text = f"{title} {content or ''}".lower()

    if keywords:
        if not any(kw.lower() in text for kw in keywords):
            return False

    if exclude_keywords:
        if any(kw.lower() in text for kw in exclude_keywords):
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_summary(title: str, content: str) -> str:
    """
    Call DeepSeek to generate a concise summary of an article.

    Args:
        title: Article title.
        content: Full article content (may be truncated).

    Returns:
        A concise summary string (typically 1-3 sentences).
    """
    system_prompt = (
        "You are a professional news analyst. Given the following article, "
        "produce a concise summary in Chinese (2-4 sentences, under 200 characters). "
        "Focus on the key facts, who is involved, what happened, and when/where if relevant. "
        "Do not add commentary or opinion."
    )

    article_text = f"标题：{title}\n\n内容：{content[:3000]}"
    messages = [{"role": "user", "content": article_text}]

    summary = await chat_with_deepseek(system_prompt, messages)
    return summary.strip()


async def process_unprocessed_articles(
    db: AsyncSession,
    topic_id: uuid.UUID,
    keywords: list[str],
    exclude_keywords: list[str],
) -> int:
    """
    Find, filter, dedup, embed, and mark processed all unprocessed articles
    belonging to sources linked to the given topic.

    Args:
        db: Async SQLAlchemy session.
        topic_id: UUID of the topic whose sources should be queried.
        keywords: Include articles matching at least one of these keywords.
        exclude_keywords: Exclude articles containing any of these keywords.

    Returns:
        Count of articles successfully processed and marked.
    """
    # 1) Collect source IDs linked to this topic
    source_ids_query = text(
        """
        SELECT source_id
        FROM topic_sources
        WHERE topic_id = :topic_id
        """
    )
    result = await db.execute(source_ids_query, {"topic_id": str(topic_id)})
    source_ids = [row[0] for row in result.fetchall()]

    if not source_ids:
        return 0

    # Format for IN clause
    placeholders = ", ".join(f":src_{i}" for i in range(len(source_ids)))
    params = {f"src_{i}": str(sid) for i, sid in enumerate(source_ids)}

    # 2) Fetch all unprocessed articles for those sources
    articles_query = text(
        f"""
        SELECT id, source_id, title, content, url, published_at
        FROM raw_articles
        WHERE source_id IN ({placeholders})
          AND is_processed = FALSE
        ORDER BY published_at DESC NULLS LAST
        """
    )
    result = await db.execute(articles_query, params)
    rows = result.fetchall()

    if not rows:
        return 0

    # 3) Build fingerprint index for dedup within this batch
    seen: dict[str, dict[str, uuid.UUID]] = {
        "urls": {},   # url_fp -> article_id
        "titles": {}, # title_fp -> article_id
    }

    processed_count = 0

    for row in rows:
        article_id, source_id, title, content, url, published_at = row
        article_id: uuid.UUID = article_id

        # --- Keyword filter ---
        if not _keyword_filter(title, content, keywords, exclude_keywords):
            continue

        # --- Dedup: check URL and title fingerprints ---
        url_fp = _url_fingerprint(url)
        title_fp = _title_fingerprint(title)

        is_dup = False

        # URL fingerprint collision → exact or near-exact duplicate
        if url_fp in seen["urls"]:
            is_dup = True

        # Title fingerprint collision within the same source
        key = (source_id, title_fp)
        if key in seen["titles"]:
            is_dup = True

        if is_dup:
            # Mark as processed but leave vector_embedding NULL (duplicate)
            await db.execute(
                text(
                    "UPDATE raw_articles SET is_processed = TRUE "
                    "WHERE id = :id"
                ),
                {"id": str(article_id)},
            )
            continue

        # Record fingerprints
        seen["urls"][url_fp] = article_id
        seen["titles"][(source_id, title_fp)] = article_id

        # --- Generate summary (optional but stored on the article) ---
        try:
            summary = await generate_summary(title, content or "")
        except Exception:
            summary = None

        # --- Generate embedding ---
        embed_text = f"{title} {content or ''}"[:8000]
        try:
            embedding = await get_embedding(embed_text)
        except Exception as e:
            # Log and skip on embedding failure
            print(f"[article_processor] embedding failed for {article_id}: {e}")
            continue

        # --- Persist ---
        await db.execute(
            text(
                """
                UPDATE raw_articles
                SET vector_embedding = :embedding,
                    summary = :summary,
                    is_processed = TRUE
                WHERE id = :id
                """
            ),
            {
                "embedding": str(embedding),
                "summary": summary,
                "id": str(article_id),
            },
        )

        processed_count += 1

    await db.commit()
    return processed_count
