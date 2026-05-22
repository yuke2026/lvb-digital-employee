"""数据库配置"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Async engine for FastAPI
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for migrations, pgvector SQL, and init scripts
# create_engine with a sync URL (postgresql://) returns a sync Engine
sync_engine: Engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


async def get_db():
    """获取数据库会话依赖注入"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db():
    """获取同步数据库会话（用于 migrations、pgvector、init scripts）"""
    with sync_engine.connect() as conn:
        try:
            yield conn
        finally:
            conn.close()


def register_vector_extension():
    """注册 pgvector 扩展（仅需调用一次）"""
    with sync_engine.connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
