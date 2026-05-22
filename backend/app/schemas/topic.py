"""Topic schemas"""
from pydantic import BaseModel, Field
from datetime import time, datetime
from typing import Optional
import uuid


class TopicBase(BaseModel):
    name: str = Field(..., max_length=100)
    category: str = Field(..., max_length=50)  # A/B/C/D/E
    keywords: list[str] = Field(...)
    exclude_keywords: list[str] = []
    push_cycle: str = "daily"  # daily/weekly/monthly
    push_time: time = time(8, 30)


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[list[str]] = None
    exclude_keywords: Optional[list[str]] = None
    push_cycle: Optional[str] = None
    push_time: Optional[time] = None
    is_active: Optional[bool] = None


class TopicResponse(TopicBase):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
