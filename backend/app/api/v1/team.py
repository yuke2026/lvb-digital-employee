"""产研团队任务管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from app.core.database import sync_engine, async_session, async_sessionmaker
from app.models.team_task import TeamTask, TaskLog
from app.core.deps import get_current_user
from sqlalchemy import select
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/v1/team", tags=["产研团队"])


# ===== 初始化表（仅首次运行时创建） =====
def _ensure_tables():
    """确保 team_tasks 和 task_logs 表存在"""
    with sync_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS team_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assignee TEXT NOT NULL,
                status TEXT DEFAULT 'backlog',
                priority TEXT DEFAULT 'P2',
                created_by TEXT DEFAULT 'user',
                conversation_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_logs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                actor TEXT DEFAULT 'system',
                message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

_ensure_tables()

# 定义合法的状态流转
STATUS_FLOW = {
    "backlog": ["design", "dev"],
    "design": ["dev", "review"],
    "dev": ["review", "qa"],
    "review": ["qa", "dev"],
    "qa": ["done", "dev"],
    "done": [],
}

STATUS_LABELS = {
    "backlog": "待办",
    "design": "设计中",
    "dev": "开发中",
    "review": "审核中",
    "qa": "测试中",
    "done": "已完成",
}


@router.get("/tasks")
async def list_tasks(
    status: str = None,
    assignee: str = None,
    current_user: dict = Depends(get_current_user),
):
    """获取任务列表"""
    async with async_session() as session:
        query = "SELECT * FROM team_tasks WHERE 1=1"
        params = {}
        if status:
            query += " AND status = :status"
            params["status"] = status
        if assignee:
            query += " AND assignee = :assignee"
            params["assignee"] = assignee
        query += " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, created_at DESC"

        result = await session.execute(text(query), params)
        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "assignee": row[3],
                "status": row[4],
                "status_label": STATUS_LABELS.get(row[4], row[4]),
                "priority": row[5],
                "created_by": row[6],
                "conversation_id": row[7],
                "created_at": row[8].isoformat() if hasattr(row[8], 'isoformat') else str(row[8]),
                "updated_at": row[9].isoformat() if row[9] and hasattr(row[9], 'isoformat') else str(row[9]) if row[9] else None,
            }
            for row in rows
        ]


@router.post("/tasks")
async def create_task(
    title: str,
    description: str = "",
    assignee: str = "PM",
    priority: str = "P2",
    created_by: str = "user",
    conversation_id: str = None,
    current_user: dict = Depends(get_current_user),
):
    """创建新任务"""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow()
    async with async_session() as session:
        await session.execute(
            text("""
                INSERT INTO team_tasks (id, title, description, assignee, status, priority, created_by, conversation_id, created_at)
                VALUES (:id, :title, :desc, :assignee, 'backlog', :priority, :created_by, :conv_id, :now)
            """),
            {
                "id": task_id,
                "title": title,
                "desc": description,
                "assignee": assignee,
                "priority": priority,
                "created_by": created_by,
                "conv_id": conversation_id,
                "now": now,
            },
        )
        # Add log
        await session.execute(
            text("""
                INSERT INTO task_logs (id, task_id, action, actor, message, created_at)
                VALUES (:id, :task_id, 'created', :actor, :msg, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "actor": created_by,
                "msg": f"创建任务: {title}",
                "now": now,
            },
        )
        await session.commit()
        return {"id": task_id, "message": "任务创建成功"}


@router.post("/tasks/{task_id}/move")
async def move_task(
    task_id: str,
    to_status: str = Query(..., description="目标状态"),
    actor: str = "system",
    message: str = "",
    current_user: dict = Depends(get_current_user),
):
    """移动任务到新状态"""
    async with async_session() as session:
        # Get current task
        result = await session.execute(
            text("SELECT * FROM team_tasks WHERE id = :id"),
            {"id": task_id},
        )
        task = result.fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        current_status = task[4]
        if to_status not in STATUS_FLOW.get(current_status, []):
            return {
                "error": True,
                "message": f"不能从「{STATUS_LABELS.get(current_status, current_status)}」直接移动到「{STATUS_LABELS.get(to_status, to_status)}」",
                "allowed": [STATUS_LABELS.get(s, s) for s in STATUS_FLOW.get(current_status, [])],
            }

        now = datetime.utcnow()
        # Update task status
        await session.execute(
            text("UPDATE team_tasks SET status = :status, updated_at = :now WHERE id = :id"),
            {"status": to_status, "now": now, "id": task_id},
        )
        # Add log
        await session.execute(
            text("""
                INSERT INTO task_logs (id, task_id, action, from_status, to_status, actor, message, created_at)
                VALUES (:id, :task_id, 'moved', :from_s, :to_s, :actor, :msg, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "from_s": current_status,
                "to_s": to_status,
                "actor": actor,
                "msg": message or f"从「{STATUS_LABELS.get(current_status, current_status)}」移动到「{STATUS_LABELS.get(to_status, to_status)}」",
                "now": now,
            },
        )
        await session.commit()
        return {"message": f"任务已移动到「{STATUS_LABELS.get(to_status, to_status)}」"}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """删除任务"""
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM task_logs WHERE task_id = :id"),
            {"id": task_id},
        )
        await session.execute(
            text("DELETE FROM team_tasks WHERE id = :id"),
            {"id": task_id},
        )
        await session.commit()
        return {"message": "任务已删除"}


@router.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, current_user: dict = Depends(get_current_user)):
    """获取任务操作日志"""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT * FROM task_logs WHERE task_id = :id ORDER BY created_at ASC"),
            {"id": task_id},
        )
        rows = result.fetchall()
        return [
            {
                "id": row[0],
                "task_id": row[1],
                "action": row[2],
                "from_status": row[3],
                "to_status": row[4],
                "actor": row[5],
                "message": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]


@router.get("/tasks/stats")
async def get_task_stats(current_user: dict = Depends(get_current_user)):
    """获取任务统计"""
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'backlog' THEN 1 ELSE 0 END) as backlog,
                SUM(CASE WHEN status = 'design' THEN 1 ELSE 0 END) as design,
                SUM(CASE WHEN status = 'dev' THEN 1 ELSE 0 END) as dev,
                SUM(CASE WHEN status = 'review' THEN 1 ELSE 0 END) as review,
                SUM(CASE WHEN status = 'qa' THEN 1 ELSE 0 END) as qa,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                SUM(CASE WHEN status != 'done' THEN 1 ELSE 0 END) as active
            FROM team_tasks
        """))
        row = result.fetchone()
        return {
            "total": row[0] or 0,
            "backlog": row[1] or 0,
            "design": row[2] or 0,
            "dev": row[3] or 0,
            "review": row[4] or 0,
            "qa": row[5] or 0,
            "done": row[6] or 0,
            "active": row[7] or 0,
        }
