"""经营分析 — API路由"""
import json, os, logging, threading, time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.data_analysis.engine import DataAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-analysis", tags=["经营分析"])

# 报告存储（prod用DB，memory用于演示）
# 格式: {report_id: AnalysisReport dict}
_reports = {}
_lock = threading.Lock()

# 安全配置
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTS = {'.xlsx', '.xls', '.csv'}
REPORT_DIR = Path(os.environ.get("ANALYSIS_REPORT_DIR", "/tmp/analysis_reports"))
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# 自动清理：30分钟前的过期文件（由定时任务调用）
def cleanup_expired(max_age_minutes: int = 30):
    now = time.time()
    for rid, report in list(_reports.items()):
        # 清理内存中30分钟前的报告
        created = report.get('created_at', '')
        try:
            from datetime import datetime
            ct = datetime.strptime(created, '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - ct).total_seconds() > max_age_minutes * 60:
                _reports.pop(rid, None)
        except:
            pass
    # 清理文件系统中过期的临时文件
    for f in REPORT_DIR.glob('*'):
        if f.is_file() and (now - f.stat().st_mtime) > max_age_minutes * 60:
            try: f.unlink()
            except: pass


def _get_storage_dir(org_id: str) -> Path:
    """创建隔离的 org 存储目录"""
    org_dir = REPORT_DIR / org_id
    org_dir.mkdir(parents=True, exist_ok=True)
    return org_dir


async def _get_org_id(db_session, user) -> str:
    if not user.org_id:
        raise HTTPException(400, "当前用户未关联企业账号")
    return str(user.org_id)


@router.post("/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    title: str = Form("经营分析报告"),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """上传Excel → 分析 → 生成HTML报告 → 自动清理原始数据"""
    org_id = await _get_org_id(db_session, current_user)

    # 验证文件
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的文件格式: {ext}，请上传 .xlsx / .xls / .csv")
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件过大（最大{MAX_FILE_SIZE//1024//1024}MB）")

    # 保存到隔离目录
    org_dir = _get_storage_dir(org_id)
    safe_name = f"{org_id}_{int(time.time())}_{file.filename}"
    save_path = org_dir / safe_name

    content = await file.read()
    with open(save_path, 'wb') as f:
        f.write(content)

    logger.info(f"[{org_id}] 收到分析请求: {file.filename} ({len(content)} bytes)")

    try:
        # 执行分析
        analyzer = DataAnalyzer(work_dir=str(org_dir / f"analysis_{int(time.time())}"))
        report = analyzer.analyze(
            excel_path=str(save_path),
            title=title,
            org_id=org_id,
        )

        # 立即删除原始上传文件
        save_path.unlink(missing_ok=True)
        logger.info(f"[{org_id}] 原始数据已删除: {save_path}")

        # 记录
        report_dict = report.to_dict()
        with _lock:
            _reports[report.report_id] = report_dict

        return {
            "success": True,
            "report_id": report.report_id,
            "title": title,
            "created_at": report.created_at,
            "message": "分析完成，原始数据已自动删除",
        }

    except Exception as e:
        logger.exception(f"[{org_id}] 分析失败: {e}")
        # 清理现场
        save_path.unlink(missing_ok=True)
        raise HTTPException(500, f"分析失败: {str(e)[:200]}")


@router.get("/reports")
async def list_reports(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """查看本企业的分析报告列表"""
    org_id = await _get_org_id(db_session, current_user)
    with _lock:
        org_reports = [r for r in _reports.values() if r.get('org_id') == org_id]
        org_reports.sort(key=lambda r: r.get('created_at', ''), reverse=True)
    return {"reports": org_reports}


@router.get("/reports/{report_id}")
async def view_report(
    report_id: str,
    fmt: str = "html",
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """查看/下载分析报告（支持格式: html/excel/ppt）"""
    org_id = await _get_org_id(db_session, current_user)

    with _lock:
        report = _reports.get(report_id)

    if not report or report.get('org_id') != org_id:
        raise HTTPException(404, "报告不存在或无权访问")

    fmt = fmt.lower()
    if fmt == "html":
        path = report.get('html_path')
        if not path or not os.path.exists(path):
            raise HTTPException(404, "HTML报告文件已过期")
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        return HTMLResponse(html)
    elif fmt == "excel":
        path = report.get('excel_path')
        if not path or not os.path.exists(path):
            raise HTTPException(404, "Excel文件已过期")
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=f"{report.get('title', '经营分析报告')}.xlsx")
    elif fmt == "ppt":
        path = report.get('ppt_path')
        if not path or not os.path.exists(path):
            raise HTTPException(404, "PPT文件已过期")
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                           filename=f"{report.get('title', '经营分析报告')}.pptx")
    else:
        raise HTTPException(400, f"不支持的格式: {fmt}，支持: html/excel/ppt")


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """删除分析报告"""
    org_id = await _get_org_id(db_session, current_user)

    with _lock:
        report = _reports.get(report_id)

    if not report or report.get('org_id') != org_id:
        raise HTTPException(404, "报告不存在或无权访问")

    # 删除文件
    html_path = report.get('html_path')
    if html_path and os.path.exists(html_path):
        os.unlink(html_path)

    with _lock:
        _reports.pop(report_id, None)

    return {"success": True, "message": "报告已删除"}
