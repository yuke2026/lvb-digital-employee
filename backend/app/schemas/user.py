"""Pydantic schemas for API request/response"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


# ===== Auth =====

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime


# ===== Employees =====

class EmployeeResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    avatar: str
    skills: list[str]
    is_active: bool

    model_config = {"from_attributes": True}


class EmployeeToggleResponse(BaseModel):
    id: str
    is_active: bool
    message: str


# ===== Chat =====

class ChatSendRequest(BaseModel):
    employee_id: str
    message: str
    conversation_id: Optional[str] = None


class ChatSendResponse(BaseModel):
    reply: str
    conversation_id: str
    skills_used: list[str] = []


class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime


class ConversationResponse(BaseModel):
    id: str
    employee_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
