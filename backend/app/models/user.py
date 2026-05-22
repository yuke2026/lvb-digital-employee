"""数据模型定义（内存模拟）"""
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel


class UserInDB(BaseModel):
    """内存中的用户模型"""
    id: str
    username: str
    email: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = datetime.now(timezone.utc)


class EmployeeInDB(BaseModel):
    """内存中的数字员工模型"""
    id: str
    name: str
    category: str
    description: str
    avatar: str
    system_prompt: str
    skills: list[str]
    is_active: bool = True
    created_at: datetime = datetime.now(timezone.utc)


class ConversationInDB(BaseModel):
    """内存中的对话模型"""
    id: str
    user_id: str
    employee_id: str
    messages: list[dict] = []
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
