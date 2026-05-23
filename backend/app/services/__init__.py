"""Services package"""
from app.services.rss_collector import fetch_rss_source
from app.services.http_crawler import fetch_http_source
from app.services.playwright_crawler import fetch_playwright_source
from app.services.redis_queue import enqueue_fetch_task, dequeue_fetch_task, mark_task_done, get_queue_stats
from app.services.embedder import get_embedding, get_embeddings_batch
from app.services.article_processor import process_unprocessed_articles, generate_summary
from app.services.report_generator import generate_report

__all__ = [
    "fetch_rss_source",
    "fetch_http_source",
    "fetch_playwright_source",
    "enqueue_fetch_task",
    "dequeue_fetch_task",
    "mark_task_done",
    "get_queue_stats",
    "get_embedding",
    "get_embeddings_batch",
    "process_unprocessed_articles",
    "generate_summary",
    "generate_report",
]
