"""FastAPI 应用入口"""
import asyncio
import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="百应智星数字员工 API 后端",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from app.api.v1 import auth, employees, chat, news_sources, topics, reports, scheduler_api

app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(employees.router, prefix="/api/v1/employees", tags=["数字员工"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["对话"])
app.include_router(news_sources.router, prefix="/api/v1/news-sources", tags=["新闻源"])
app.include_router(topics.router, prefix="/api/v1/topics", tags=["主题"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["报告"])
app.include_router(scheduler_api.router, prefix="/api/v1/scheduler", tags=["调度管理"])


@app.get("/api/health", include_in_schema=False)
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": settings.APP_VERSION, "app": "百应智星"}


# =====================================================
# 综合健康检查端点
# =====================================================
async def check_db_health():
    """检查数据库连接"""
    try:
        from sqlalchemy import text
        from app.core.database import async_session
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        return f"error: {str(e)[:50]}"


def check_redis_health_sync():
    """检查Redis连接 (同步)"""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        return "ok"
    except Exception as e:
        return f"error: {str(e)[:50]}"


async def check_redis_health():
    """检查Redis连接"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_redis_health_sync)


async def check_deepseek_health():
    """检查DeepSeek API连通性"""
    if not settings.DEEPSEEK_API_KEY:
        return "skipped"
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
                timeout=5.0
            )
            if response.status_code == 200:
                return "ok"
            return f"error: status {response.status_code}"
    except Exception as e:
        return f"error: {str(e)[:50]}"


@app.get("/health", tags=["监控"])
async def comprehensive_health_check():
    """
    综合健康检查
    返回状态: healthy (所有检查通过), degraded (部分通过), unhealthy (全部失败)
    """
    db_status = await check_db_health()
    redis_status = await check_redis_health()
    deepseek_status = await check_deepseek_health()

    all_ok = db_status == "ok" and redis_status == "ok"
    any_ok = db_status == "ok" or redis_status == "ok"

    status = "healthy" if all_ok else ("degraded" if any_ok else "unhealthy")

    return {
        "status": status,
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": db_status,
            "redis": redis_status,
            "deepseek_api": deepseek_status
        }
    }


@app.get("/ready", tags=["监控"])
async def readiness_check():
    """Kubernetes readiness probe - 检查应用是否可处理请求"""
    return {"status": "ready"}


# =====================================================


# 前端 SPA 路由
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend"
)
INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")


@app.get("/")
async def serve_root():
    """首页"""
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html")
    return HTMLResponse("<h1>前端未构建</h1><p>请先构建前端文件</p>", status_code=200)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """SPA 路由：所有非 API、非静态文件的 404 都返回前端 index.html"""
    path = request.url.path
    if path.startswith("/api/"):
        return HTMLResponse('{"detail":"Not Found"}', status_code=404, media_type="application/json")
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html")
    return HTMLResponse("<h1>Not Found</h1>", status_code=404)
