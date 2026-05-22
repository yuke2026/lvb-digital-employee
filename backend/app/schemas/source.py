"""News source schemas"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
import uuid


class NewsSourceBase(BaseModel):
    name: str = Field(..., max_length=100)
    source_type: str = Field(...)  # rss/api/crawl
    url: str = Field(...)
    update_freq: str = "1h"
    config: Optional[dict[str, Any]] = {}


class NewsSourceCreate(NewsSourceBase):
    pass


class NewsSourceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    url: Optional[str] = None
    update_freq: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class NewsSourceResponse(NewsSourceBase):
    id: uuid.UUID
    is_active: bool
    last_fetch_at: Optional[datetime] = None
    last_fetch_status: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
