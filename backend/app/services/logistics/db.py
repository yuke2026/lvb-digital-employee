"""驿递通 · 操作日志 SQLite 存储"""
import sqlite3
import json
import time
import os
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger("驿递通.db")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "operations.db")


class OperationDB:
    """操作日志数据库"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                operation_type TEXT NOT NULL,
                mail_no TEXT,
                txlogistic_id TEXT,
                request_params TEXT,
                response_data TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                operator_name TEXT,
                operator_id TEXT,
                feishu_chat_id TEXT,
                callback_received INTEGER DEFAULT 0,
                callback_result TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ops_mail_no ON operations(mail_no);
            CREATE INDEX IF NOT EXISTS idx_ops_status ON operations(status);
            CREATE INDEX IF NOT EXISTS idx_ops_created ON operations(created_at);
        """)
        conn.commit()
        conn.close()

    def log_operation(self, operation_type: str, mail_no: str = None,
                      txlogistic_id: str = None,
                      request_params: dict = None,
                      operator_name: str = None,
                      operator_id: str = None,
                      feishu_chat_id: str = None) -> int:
        """记录操作"""
        conn = self._conn()
        cursor = conn.execute(
            """INSERT INTO operations
               (operation_type, mail_no, txlogistic_id, request_params,
                status, operator_name, operator_id, feishu_chat_id)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (operation_type, mail_no, txlogistic_id,
             json.dumps(request_params, ensure_ascii=False) if request_params else None,
             operator_name, operator_id, feishu_chat_id)
        )
        op_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"[DB] 记录操作 #{op_id}: {operation_type} {mail_no or txlogistic_id}")
        return op_id

    def update_result(self, op_id: int, status: str,
                      response_data: dict = None,
                      error_message: str = None):
        """更新操作结果"""
        conn = self._conn()
        conn.execute(
            """UPDATE operations SET status=?, response_data=?,
               error_message=?, updated_at=datetime('now','localtime')
               WHERE id=?""",
            (status,
             json.dumps(response_data, ensure_ascii=False) if response_data else None,
             error_message, op_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"[DB] 更新操作 #{op_id}: {status}")

    def record_callback(self, mail_no: str, callback_result: str,
                        return_mail_no: str = None):
        """记录极兔拦截回传"""
        conn = self._conn()
        conn.execute(
            """UPDATE operations SET callback_received=1,
               callback_result=?, updated_at=datetime('now','localtime')
               WHERE mail_no=? AND callback_received=0""",
            (f"{callback_result}|{return_mail_no or ''}", mail_no)
        )
        conn.commit()
        conn.close()
        logger.info(f"[DB] 回传记录: {mail_no} → {callback_result}")

    def get_recent(self, limit: int = 20) -> list[dict]:
        """获取最近的操作记录"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM operations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_by_mail_no(self, mail_no: str) -> list[dict]:
        """按运单号查询"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM operations WHERE mail_no=? ORDER BY id DESC", (mail_no,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# 全局单例
db = OperationDB()
