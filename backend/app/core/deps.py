"""依赖注入"""
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.security import decode_access_token
from app.core.database import get_db
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    token: str = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """获取当前登录用户（从JWT解码并查询数据库）"""
    credentials = await decode_access_token(token.credentials)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = credentials.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌格式错误",
        )
    
    # JWT stores sub as string UUID, convert to UUID for DB query
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )
    
    return user


async def get_current_user_optional(
    token: str | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    """可选的当前用户（token不存在也返回None）"""
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None
