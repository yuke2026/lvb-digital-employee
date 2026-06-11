"""经营分析 — API路由"""
import json, os, logging, threading, time, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.data_analysis.engine import DataAnalyzer
from app.services.data_analysis.engine_v2 import MultiTableAnalyzer
from app.services.ai import chat_with_deepseek

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


# ═══════════════════════════════════════════════
# V2 — 多表灵活分析
# ═══════════════════════════════════════════════

# 多表分析会话存储
_analysis_sessions = {}
_session_lock = threading.Lock()

@router.post("/upload-multi")
async def upload_multi(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """上传1-5个文件，返回各表的schema信息"""
    org_id = await _get_org_id(db_session, current_user)

    if len(files) < 1 or len(files) > 5:
        raise HTTPException(400, "请上传1-5个文件")
    if sum((f.size or 0) for f in files) > 5 * MAX_FILE_SIZE:
        raise HTTPException(400, "文件总大小超过限制")

    session_id = str(uuid.uuid4())[:12]
    session_dir = REPORT_DIR / org_id / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    analyzer = MultiTableAnalyzer(work_dir=str(session_dir))
    tables = []

    for f in files:
        ext = os.path.splitext(f.filename or '')[1].lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的文件格式: {ext}")
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        save_path = session_dir / safe_name
        content = await f.read()
        with open(save_path, 'wb') as wf:
            wf.write(content)
        schema = analyzer.load_table(str(save_path), table_id=safe_name[:8])
        tables.append({
            'table_id': schema['table_id'],
            'filename': f.filename,
            'cols': schema['cols'],
            'columns': schema['columns'],
            'rows': schema['rows'],
        })

    with _session_lock:
        _analysis_sessions[session_id] = {
            'analyzer': analyzer,
            'org_id': org_id,
            'tables': tables,
            'created_at': time.time(),
        }

    logger.info(f"[{org_id}] 多表上传: session={session_id}, {len(tables)}个表")
    return {
        "success": True,
        "session_id": session_id,
        "tables": tables,
    }


@router.post("/preview/{session_id}/{table_id}")
async def preview_table(
    session_id: str, table_id: str,
    n: int = Form(20),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """预览表中前n行数据"""
    org_id = await _get_org_id(db_session, current_user)
    sess = _analysis_sessions.get(session_id)
    if not sess or sess['org_id'] != org_id:
        raise HTTPException(404, "会话不存在或已过期")
    data = sess['analyzer'].preview(table_id, n=n)
    return {"success": True, "data": data}


@router.post("/analyze-custom")
async def analyze_custom(
    data: dict,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """执行自定义多表分析
    请求体:
    {
        session_id: str,
        joins: [{left_table, left_col, right_table, right_col, how}],
        row_dims: [{column, label}],
        col_dims: [{column, label}],
        values: [{column, agg, label}],
        filters: [{column, op, value}],
        title: str
    }
    """
    org_id = await _get_org_id(db_session, current_user)
    session_id = data.get('session_id')
    sess = _analysis_sessions.get(session_id)
    if not sess or sess['org_id'] != org_id:
        raise HTTPException(404, "会话不存在或已过期")

    analyzer = sess['analyzer']
    joins = data.get('joins', [])
    row_dims = data.get('row_dims', [])
    col_dims = data.get('col_dims', [])
    values = data.get('values', [])
    filters = data.get('filters', [])
    title = data.get('title', '经营分析报告')

    try:
        # 1. 合并
        if joins:
            merged_df = analyzer.merge(joins)
        else:
            merged_df = list(analyzer.tables.values())[0]

        # 2. 聚合
        aggr_result = analyzer.aggregate(
            merged_df,
            row_dims=row_dims,
            col_dims=col_dims,
            values=values,
            filters=filters,
        )

        # 3. 生成HTML报告
        html, report_id = analyzer.build_html_report(
            title=title,
            aggr_result=aggr_result,
            join_info=joins,
            org_id=org_id,
        )

        # 保存报告文件
        report_path = REPORT_DIR / org_id / f"{report_id}.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # 记录到内存
        report_dict = {
            'report_id': report_id,
            'org_id': org_id,
            'title': title,
            'html_path': str(report_path),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        with _lock:
            _reports[report_id] = report_dict

        logger.info(f"[{org_id}] 自定义分析完成: {report_id}")

        return {
            "success": True,
            "report_id": report_id,
            "title": title,
            "created_at": report_dict['created_at'],
            "aggregation": aggr_result,
        }

    except Exception as e:
        logger.exception(f"[{org_id}] 自定义分析失败: {e}")
        raise HTTPException(500, f"分析失败: {str(e)[:300]}")


@router.post("/ai-recommend")
async def ai_recommend_dimensions(
    data: dict,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """AI推荐分析维度"""
    org_id = await _get_org_id(db_session, current_user)
    tables = data.get('tables', [])
    joins = data.get('joins', [])

    # 构造prompt
    table_desc = []
    for t in tables:
        cols_desc = '\n'.join(f'  - {c["name"]} ({c["type"]}, 唯一值{c["unique"]}个)'
                              for c in t.get('columns', []))
        table_desc.append(f'表 "{t.get("filename", "未知")}":\n{cols_desc}')

    join_desc = ''
    if joins:
        join_desc = '表关联:\n' + '\n'.join(
            f'  {j["left_table"]}.{j["left_col"]} = {j["right_table"]}.{j["right_col"]}'
            for j in joins
        )

    prompt = f"""你是一个数据分析专家。用户上传了以下表格，请推荐最有价值的分析维度。

{table_desc}

{join_desc}

请推荐5-8个分析组合，按分析价值排序。每个组合包含:
- row: 行维度(分组字段)
- values: 聚合指标(数值字段)
- agg: 聚合方式(sum/avg/count)
- label: 易懂的中文标签
- reason: 为什么这么分析

以JSON数组返回，格式:
[{{"row": "字段名", "values": ["字段名"], "agg": "sum", "label": "...","reason": "..."}}]

只返回JSON数组，不要其他内容。"""

    try:
        # 调用内部AI服务
        content = await chat_with_deepseek(
            system_prompt="你是一个数据分析专家，擅长从表格数据中推荐分析维度。只返回JSON数组。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        if not content:
            raise ValueError("AI返回为空")
    except Exception as e:
        logger.warning(f"AI推荐失败，返回默认建议: {e}")
        content = json.dumps([
            {"row": list(tables[0]['columns'])[0]['name'] if tables else "字段",
             "values": [c['name'] for c in (tables[0]['columns'] if tables else []) if c['type'] == '数值'][:1] or ["计数"],
             "agg": "sum", "label": "基础汇总", "reason": "查看数据全貌"}
        ])

    try:
        recommendations = json.loads(content)
    except:
        recommendations = []

    return {"success": True, "recommendations": recommendations}


@router.post("/ai-insights")
async def ai_insights(
    data: dict,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """AI分析洞察——对分析结果生成解读"""
    org_id = await _get_org_id(db_session, current_user)
    aggr = data.get('aggregation', {})
    dims = aggr.get('dimensions', {})
    chart_data = aggr.get('data', [])
    total_val = sum(r.get(list(r.keys())[-1], 0) for r in chart_data) if chart_data else 0

    prompt = f"""你是一个数据分析专家。以下是一组数据分析结果，请生成一份简洁的商业洞察报告。

分析配置:
- 行维度: {dims.get('row', [{}])[0].get('label', '未知') if dims.get('row') else '未知'}
- 聚合指标: {dims.get('values', [{}])[0].get('label', '未知') if dims.get('values') else '未知'}
- 聚合方式: {dims.get('values', [{}])[0].get('agg', 'sum') if dims.get('values') else 'sum'}

数据样例（前15行）:
{json.dumps(chart_data[:15], ensure_ascii=False, indent=2)}

请输出:
1. 📊 核心发现（3-5条，用数据说话）
2. 🔍 关键洞察（趋势、异常、分布特征）
3. 💡 业务建议（2-3条可执行建议）

用中文，简洁有力，每点一句话。"""

    try:
        insights = await chat_with_deepseek(
            system_prompt="你是一个数据分析专家，擅长从数据中发现商业洞察。用中文输出。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1536,
        )
        if not insights:
            insights = "AI洞察暂时不可用"
    except Exception as e:
        logger.warning(f"AI洞察生成失败: {e}")
        insights = "AI洞察暂时不可用"

    return {"success": True, "insights": insights}
