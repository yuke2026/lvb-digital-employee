"""认证路由：注册、登录、获取当前用户"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.user import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from app.core.security import create_access_token, verify_password
from app.core.deps import get_current_user
from app.services.db import db

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    """注册新用户"""
    # 检查邮箱是否已注册
    if db.get_user_by_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册",
        )

    # 检查用户名是否已存在
    if db.get_user_by_username(req.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用",
        )

    # 创建用户
    user = db.create_user(
        username=req.username,
        email=req.email,
        password=req.password,
    )

    # 生成 token
    token = create_access_token({"sub": user.id, "email": user.email})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """用户登录"""
    user = db.get_user_by_email(req.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    token = create_access_token({"sub": user.id, "email": user.email})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    user_id = current_user.get("sub")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )
