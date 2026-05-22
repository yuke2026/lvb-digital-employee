"""FastAPI 应用入口"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="联想百应数字员工 API 后端",
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

# 注册路由（必须在静态文件路由之前）
from app.api.v1 import auth, employees, chat

app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(employees.router, prefix="/api/v1/employees", tags=["数字员工"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["对话"])


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": settings.APP_VERSION}


# 前端 SPA 路由
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend"
)
INDEX_HTML = os.path.join(FRONTEND_DIR, "index.html")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """为 SPA 提供前端文件，非 API 路径返回 index.html"""
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html")
    return HTMLResponse("<h1>前端未构建</h1><p>请先构建前端文件</p>", status_code=200)
