"""Pydantic schemas for user/authentication"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: str = Field(..., max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    org_id: Optional[uuid.UUID] = None


class UserRegister(UserBase):
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    phone: Optional[str] = None
    role: str
    org_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


# ===== Legacy compatibility =====

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# ===== Legacy in-memory DB models (used by services/db.py) =====

class UserInDB(BaseModel):
    id: str
    username: str
    email: str
    hashed_password: str
    is_active: bool
    created_at: datetime


class EmployeeInDB(BaseModel):
    id: str
    name: str
    category: str
    description: str
    avatar: str
    system_prompt: str
    skills: list[str]
    is_active: bool
    created_at: datetime


class ConversationInDB(BaseModel):
    id: str
    user_id: str
    employee_id: str
    messages: list[dict]
    created_at: datetime
    updated_at: datetime


# ===== Employee schemas =====

class EmployeeResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    avatar: str
    skills: list[str]
    is_active: bool


class EmployeeToggleResponse(BaseModel):
    id: str
    is_active: bool
    message: str


# ===== Chat schemas =====

class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    employee_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ChatSendRequest(BaseModel):
    employee_id: str
    message: str
    conversation_id: Optional[str] = None
