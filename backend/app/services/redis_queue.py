"""Redis Streams task queue for fetch tasks."""

import uuid
from typing import Optional

import redis

STREAM_KEY = "fetch:tasks"
CONSUMER_GROUP = "fetch-workers"
CONSUMER_NAME = f"worker-{uuid.uuid4().hex[:8]}"

_client: Optional[redis.Redis] = None


def get_client() -> redis.Redis:
    """Get or create the Redis client (singleton)."""
    global _client
    if _client is None:
        _client = redis.Redis(decode_responses=True)
    return _client


def _ensure_group(r: redis.Redis) -> None:
    """Create the consumer group if it doesn't exist."""
    try:
        r.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def enqueue_fetch_task(source_id: str, source_type: str) -> str:
    """
    Add a new fetch task to the stream.

    Returns the task_id (message ID) assigned by Redis.
    """
    r = get_client()
    task_id = r.xadd(
        STREAM_KEY,
        {
            "source_id": source_id,
            "source_type": source_type,
            "status": "pending",
        },
    )
    return task_id


def dequeue_fetch_task(block_ms: int = 5000) -> Optional[dict]:
    """
    Block and consume a single task from the stream via the consumer group.

    Returns a dict with task_id, source_id, source_type, status,
    or None if the timeout was reached.
    """
    r = get_client()
    _ensure_group(r)

    streams = {STREAM_KEY: ">"}
    result = r.xreadgroup(
        groupname=CONSUMER_GROUP,
        consumername=CONSUMER_NAME,
        streams=streams,
        count=1,
        block=block_ms,
    )

    if not result:
        return None

    # result format: [(stream_key, [(message_id, {field: value, ...])])]
    _, messages = result[0]
    if not messages:
        return None

    message_id, fields = messages[0]
    return {
        "task_id": message_id,
        "source_id": fields.get("source_id", ""),
        "source_type": fields.get("source_type", ""),
        "status": fields.get("status", ""),
    }


def mark_task_done(task_id: str) -> None:
    """Acknowledge a task as completed (remove from pending)."""
    r = get_client()
    r.xack(STREAM_KEY, CONSUMER_GROUP, task_id)


def get_queue_stats() -> dict:
    """Return current queue statistics."""
    r = get_client()

    stream_len = r.xlen(STREAM_KEY)

    # Count pending messages for this consumer group
    pending_info = r.xpending(STREAM_KEY, CONSUMER_GROUP)
    if pending_info and isinstance(pending_info, (list, tuple)):
        pending_count = pending_info[0] if pending_info else 0
    else:
        pending_count = 0

    # Get consumer list and count
    consumer_info = r.xinfo_consumers(STREAM_KEY, CONSUMER_GROUP)
    consumer_count = len(consumer_info) if consumer_info else 0

    return {
        "stream_len": stream_len,
        "pending": pending_count,
        "consumers": consumer_count,
    }
