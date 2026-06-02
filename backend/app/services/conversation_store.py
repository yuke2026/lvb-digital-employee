"""对话存储（SQLite 持久化）"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_conversations_table(db: AsyncSession):
    """确保 conversations 表存在"""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            messages TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await db.commit()


async def create_conversation(db: AsyncSession, user_id: str, employee_id: str) -> dict:
    """创建新对话并返回对话数据"""
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    messages_json = '[]'
    await db.execute(
        text("""
            INSERT INTO conversations (id, user_id, employee_id, messages, created_at, updated_at)
            VALUES (:id, :user_id, :employee_id, :messages, :created_at, :updated_at)
        """),
        {
            "id": conv_id,
            "user_id": user_id,
            "employee_id": employee_id,
            "messages": messages_json,
            "created_at": now,
            "updated_at": now,
        }
    )
    await db.commit()
    return _row_to_dict(conv_id, user_id, employee_id, [], now, now)


def _row_to_dict(id, user_id, employee_id, messages, created_at, updated_at):
    msgs = messages if isinstance(messages, list) else json.loads(messages)
    return {
        "id": id,
        "user_id": user_id,
        "employee_id": employee_id,
        "messages": msgs,
        "created_at": created_at,
        "updated_at": updated_at,
    }


async def get_conversation(db: AsyncSession, conversation_id: str) -> Optional[dict]:
    """获取单个对话"""
    result = await db.execute(
        text("SELECT id, user_id, employee_id, messages, created_at, updated_at FROM conversations WHERE id = :id"),
        {"id": conversation_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return _row_to_dict(*row)


async def add_message(db: AsyncSession, conversation_id: str, role: str, content: str):
    """向对话中添加一条消息"""
    conv = await get_conversation(db, conversation_id)
    if not conv:
        return
    now = datetime.now(timezone.utc)
    msg = {"role": role, "content": content, "timestamp": now}
    conv["messages"].append(msg)
    await db.execute(
        text("UPDATE conversations SET messages = :messages, updated_at = :updated_at WHERE id = :id"),
        {
            "messages": json.dumps(conv["messages"], default=str),
            "updated_at": now,
            "id": conversation_id,
        }
    )
    await db.commit()


async def list_conversations(db: AsyncSession, user_id: str) -> list[dict]:
    """获取用户的所有对话，按更新时间倒序"""
    result = await db.execute(
        text("""
            SELECT id, user_id, employee_id, messages, created_at, updated_at
            FROM conversations
            WHERE user_id = :user_id
            ORDER BY updated_at DESC
        """),
        {"user_id": user_id},
    )
    rows = result.fetchall()
    return [_row_to_dict(*row) for row in rows]


async def delete_conversation(db: AsyncSession, conversation_id: str, user_id: str) -> bool:
    """删除单个对话（仅限自己的）"""
    result = await db.execute(
        text("DELETE FROM conversations WHERE id = :id AND user_id = :user_id"),
        {"id": conversation_id, "user_id": user_id},
    )
    await db.commit()
    return result.rowcount > 0


async def clear_conversations(db: AsyncSession, user_id: str) -> int:
    """清空用户的所有对话，返回删除数量"""
    result = await db.execute(
        text("DELETE FROM conversations WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    await db.commit()
    return result.rowcount
