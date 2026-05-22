"""Memory schemas"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


class MemoryBase(BaseModel):
    content: str = Field(...)
    memory_type: str  # ceo_profile/org_profile/topic_tracking/conversation
    tags: list[str] = []
    importance: float = 0.5


class MemoryCreate(MemoryBase):
    user_id: Optional[uuid.UUID] = None
    source: Optional[str] = None
    source_id: Optional[uuid.UUID] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    importance: Optional[float] = None
    is_active: Optional[bool] = None


class MemoryResponse(MemoryBase):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    source: Optional[str] = None
    source_id: Optional[uuid.UUID] = None
    is_active: bool
    access_count: int
    last_accessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    similarity: Optional[float] = None  # for search results

    model_config = {"from_attributes": True}


class MemorySearchResponse(BaseModel):
    results: list[MemoryResponse]
    total: int
