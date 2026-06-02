"""报告 PDF 下载路由"""
import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/reports", tags=["报告PDF"])

# ===== Helpers =====

def _parse_json(v):
    """Parse JSON string from DB if needed. Returns dict/list or None."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return None
    return v


def _swot_blocks(swot: dict) -> dict:
    """Extract non-empty SWOT blocks."""
    labels = {
        "s": ("[优势] Strengths", "emerald"),
        "w": ("[劣势] Weaknesses", "red"),
        "o": ("[机会] Opportunities", "blue"),
        "t": ("[威胁] Threats", "yellow"),
    }
    blocks = {}
    for key, (label, color) in labels.items():
        text_content = (swot.get(key) or "").strip()
        if text_content:
            blocks[key] = {"label": label, "text": text_content, "color": color}
    return blocks


def _wrap_text(text: str, max_width_chars: int = 85) -> str:
    """Simple word-wrap for CJK text — insert newlines at max_width_chars."""
    if not text:
        return ""
    lines = []
    pos = 0
    while pos < len(text):
        chunk = text[pos:pos + max_width_chars]
        # Try to break at a Chinese period or space for readability
        if len(chunk) == max_width_chars and pos + max_width_chars < len(text):
            break_at = max(
                chunk.rfind("。"), chunk.rfind("，"),
                chunk.rfind("."), chunk.rfind(" "),
                chunk.rfind("；"),
            )
            if break_at > max_width_chars // 2:
                lines.append(chunk[:break_at + 1])
                pos += break_at + 1
                continue
        lines.append(chunk)
        pos += len(chunk)
    return "\n".join(lines)


# ===== PDF generation using pure Python (fpdf2) =====

def _generate_report_pdf(report: dict) -> bytes:
    """
    Generate a PDF for the given report data using fpdf2.
    Falls back to plain text PDF if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        # Fallback: minimal text-only PDF
        return _generate_text_pdf(report)
    
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    
    # ── Font: WenQuanYi Zen Hei for full CJK support ──
    try:
        pdf.add_font("WQY", "", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
        pdf.add_font("WQY", "B", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
        has_font = True
    except Exception:
        has_font = False
    
    # Margins
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)
    pdf.set_top_margin(15)
    page_w = 210 - 40  # usable width (A4 = 210mm, minus margins)
    
    def write_line(text, style="", size=10, bold=False):
        if has_font:
            pdf.set_font("WQY", "B" if bold else "", size)
        pdf.multi_cell(page_w, 6, text, new_x="LMARGIN", new_y="NEXT")
    
    # ── Title ──
    if has_font:
        pdf.set_font("WQY", "B", 16)
    pdf.set_text_color(30, 30, 30)
    title = report.get("title", "报告详情")
    pdf.multi_cell(page_w, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    # ── Separator ──
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(4)
    
    # ── Meta info ──
    if has_font:
        pdf.set_font("WQY", "", 9)
    pdf.set_text_color(120, 120, 120)
    type_labels = {"daily": "日报", "weekly": "周报", "monthly": "月报", "quarterly": "季报", "yearly": "年报"}
    meta_parts = []
    meta_parts.append(f"类型：{type_labels.get(report.get('report_type', ''), report.get('report_type', ''))}")
    if report.get("created_at"):
        try:
            meta_parts.append(f"创建时间：{str(report['created_at'])[:19]}")
        except Exception:
            pass
    risk_level = report.get("risk_level") or ""
    level_map = {"高": "🔴 高风险", "中": "🟡 中风险", "低": "🟢 低风险", 
                 "high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}
    if risk_level:
        meta_parts.append(f"风险等级：{level_map.get(risk_level, risk_level)}")
    
    pdf.cell(page_w, 5, " | ".join(meta_parts), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # ── Summary ──
    summary = (report.get("summary") or "").strip()
    if summary:
        pdf.set_draw_color(100, 149, 237)
        pdf.set_fill_color(240, 248, 255)
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        pdf.rect(x0, y0, page_w, 2, style="F")  # thin top bar
        pdf.ln(3)
        if has_font:
            pdf.set_font("WQY", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(page_w, 6, "-- 摘要", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        if has_font:
            pdf.set_font("WQY", "", 9.5)
        pdf.set_text_color(60, 60, 60)
        wrapped = _wrap_text(summary, 90)
        pdf.multi_cell(page_w, 5, wrapped, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    
    # ── SWOT Analysis ──
    swot_raw = _parse_json(report.get("swot")) or {}
    swot_blocks = _swot_blocks(swot_raw)
    if swot_blocks:
        if has_font:
            pdf.set_font("WQY", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(page_w, 6, ">> SWOT 分析", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        color_map = {
            "emerald": (16, 185, 129), "red": (239, 68, 68),
            "blue": (59, 130, 246), "yellow": (234, 179, 8),
        }
        bg_map = {
            "emerald": (236, 253, 245), "red": (254, 242, 242),
            "blue": (239, 246, 255), "yellow": (254, 252, 232),
        }
        
        # Single-column layout for SWOT (cleaner for PDF)
        cols = list(swot_blocks.items())
        col_colors = {"emerald": (16,185,129), "red": (239,68,68), "blue": (59,130,246), "yellow": (234,179,8)}
        col_bgs = {"emerald": (236,253,245), "red": (254,242,242), "blue": (239,246,255), "yellow": (254,252,232)}
        
        for key, block in cols:
            color = col_colors.get(block["color"], (100,100,100))
            bg = col_bgs.get(block["color"], (248,248,248))
            
            y0 = pdf.get_y()
            # Check if we need a new page (leave room for at least 3 lines)
            if y0 > 260:
                pdf.add_page()
                y0 = pdf.get_y()
            
            # Draw background and left color bar (before text, so text is on top)
            pdf.set_fill_color(*bg)
            pdf.rect(pdf.l_margin, y0, page_w, 50, style="F")
            pdf.set_fill_color(*color)
            pdf.rect(pdf.l_margin, y0, 2.5, 50, style="F")
            
            # Title
            if has_font:
                pdf.set_font("WQY", "B", 10)
            pdf.set_text_color(*color)
            pdf.set_xy(pdf.l_margin + 8, y0 + 3)
            pdf.cell(page_w - 12, 5, block["label"], new_x="LMARGIN", new_y="NEXT")
            
            # Text
            if has_font:
                pdf.set_font("WQY", "", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.set_x(pdf.l_margin + 8)
            pdf.multi_cell(page_w - 12, 5.5, block["text"], new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(3)
    
    # ── Risks ──
    risk_items = _parse_json(report.get("risk_items")) or {}
    risks = risk_items.get("risks", []) if isinstance(risk_items, dict) else []
    if risks:
        if has_font:
            pdf.set_font("WQY", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(page_w, 6, ">> 风险识别", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        level_colors = {"高": (239,68,68), "中": (234,179,8), "低": (16,185,129),
                        "high": (239,68,68), "medium": (234,179,8), "low": (16,185,129)}
        level_bg = {"高": (254,242,242), "中": (254,252,232), "低": (236,253,245),
                    "high": (254,242,242), "medium": (254,252,232), "low": (236,253,245)}
        
        for r in risks[:10]:
            title = r.get("title", "")
            desc = r.get("description", "")
            lvl = r.get("level", "中")
            
            pdf.set_fill_color(*level_bg.get(lvl, (245,245,245)))
            y0 = pdf.get_y()
            pdf.rect(pdf.l_margin, y0, page_w, 1, style="F")  # thin fill top
            pdf.ln(1)
            
            if has_font:
                pdf.set_font("WQY", "B", 9)
            pdf.set_text_color(*level_colors.get(lvl, (100,100,100)))
            level_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}
            pdf.cell(page_w, 5, f"{level_icon.get(lvl, '▪')} [{lvl}] {title}", new_x="LMARGIN", new_y="NEXT")
            
            if desc:
                if has_font:
                    pdf.set_font("WQY", "", 8.5)
                pdf.set_text_color(80, 80, 80)
                pdf.set_x(pdf.l_margin + 4)
                wrapped = _wrap_text(desc, 85)
                pdf.multi_cell(page_w - 4, 4.5, wrapped, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        
        pdf.ln(2)
    
    # ── Opportunities ──
    opps_data = _parse_json(report.get("opportunities")) or {}
    opps = opps_data.get("opportunities", []) if isinstance(opps_data, dict) else []
    if opps:
        if has_font:
            pdf.set_font("WQY", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(page_w, 6, ">> 机会发现", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        for o in opps[:10]:
            title = o.get("title", "")
            desc = o.get("description", "")
            potential = o.get("potential", "")
            timeline = o.get("timeline", "")
            
            pdf.set_fill_color(240, 248, 255)
            y0 = pdf.get_y()
            pdf.rect(pdf.l_margin, y0, page_w, 1, style="F")
            pdf.ln(1)
            
            if has_font:
                pdf.set_font("WQY", "B", 9)
            pdf.set_text_color(30, 64, 175)
            pdf.cell(page_w, 5, f"✨ {title}", new_x="LMARGIN", new_y="NEXT")
            
            if desc:
                if has_font:
                    pdf.set_font("WQY", "", 8.5)
                pdf.set_text_color(80, 80, 80)
                pdf.set_x(pdf.l_margin + 4)
                wrapped = _wrap_text(desc, 85)
                pdf.multi_cell(page_w - 4, 4.5, wrapped, new_x="LMARGIN", new_y="NEXT")
            
            detail_parts = []
            if potential:
                detail_parts.append(f"潜力：{potential}")
            if timeline:
                detail_parts.append(f"时机：{timeline}")
            if detail_parts:
                if has_font:
                    pdf.set_font("WQY", "", 8)
                pdf.set_text_color(120, 120, 120)
                pdf.set_x(pdf.l_margin + 4)
                pdf.cell(page_w - 4, 4.5, " | ".join(detail_parts), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        
        pdf.ln(2)
    
    # ── Source Articles ──
    content_raw = _parse_json(report.get("content")) or {}
    articles = content_raw.get("articles", []) if isinstance(content_raw, dict) else []
    if articles:
        # Check if we have space
        if pdf.get_y() > 250:
            pdf.add_page()
        
        if has_font:
            pdf.set_font("WQY", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(page_w, 6, f"源文章快照（{len(articles)}篇）", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        
        for i, art in enumerate(articles[:20]):
            title = art.get("title", "")
            summary = (art.get("summary") or "")[:150]
            art_url = art.get("url", "")
            
            if has_font:
                pdf.set_font("WQY", "B", 8.5)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(page_w, 5, f"{i+1}. {title}", new_x="LMARGIN", new_y="NEXT")
            
            if summary:
                if has_font:
                    pdf.set_font("WQY", "", 8)
                pdf.set_text_color(100, 100, 100)
                pdf.set_x(pdf.l_margin + 4)
                wrapped = _wrap_text(summary, 85)
                pdf.multi_cell(page_w - 4, 4, wrapped, new_x="LMARGIN", new_y="NEXT")
            
            if art_url and len(art_url) < 200:
                if has_font:
                    pdf.set_font("WQY", "", 7)
                pdf.set_text_color(100, 149, 237)
                pdf.set_x(pdf.l_margin + 4)
                pdf.cell(page_w - 4, 3.5, f"🔗 {art_url[:120]}", new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(1)
    
    # ── Footer ──
    pdf.ln(5)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)
    if has_font:
        pdf.set_font("WQY", "", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(page_w, 4, f"由百应智星生成 · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", new_x="LMARGIN", new_y="NEXT")
    
    return bytes(pdf.output())


def _generate_text_pdf(report: dict) -> bytes:
    """Fallback: generate a minimal text-based PDF when fpdf2 is not available."""
    title = report.get("title", "Report")
    summary = report.get("summary", "")
    swot_raw = _parse_json(report.get("swot")) or {}
    risk_items = _parse_json(report.get("risk_items")) or {}
    opps_data = _parse_json(report.get("opportunities")) or {}
    
    lines = [
        f"Title: {title}",
        f"Type: {report.get('report_type', '')}",
        f"Risk: {report.get('risk_level', '')}",
        f"Created: {report.get('created_at', '')}",
        "=" * 72,
        "",
        "SUMMARY",
        "-" * 72,
        summary,
        "",
        "SWOT ANALYSIS",
        "-" * 72,
        f"S: {swot_raw.get('s', '')}",
        f"W: {swot_raw.get('w', '')}",
        f"O: {swot_raw.get('o', '')}",
        f"T: {swot_raw.get('t', '')}",
        "",
        "RISKS",
        "-" * 72,
    ]
    risks = risk_items.get("risks", []) if isinstance(risk_items, dict) else []
    for r in risks:
        lines.append(f"[{r.get('level', '?')}] {r.get('title', '')}: {r.get('description', '')}")
    
    lines += ["", "OPPORTUNITIES", "-" * 72]
    opps = opps_data.get("opportunities", []) if isinstance(opps_data, dict) else []
    for o in opps:
        lines.append(f"* {o.get('title', '')}: {o.get('description', '')}")
    
    text = "\n".join(lines)
    
    # Minimal PDF via reportlab-style raw PDF
    text_escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    pdf_content = (
        "%PDF-1.4\n"
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        "/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        f"4 0 obj<</Length {len(text) * 3 + 100}>>stream\n"
        "BT\n"
        "/F1 10 Tf\n"
        f"50 742 Td\n"
        f"({text_escaped}) Tj\n"
        "ET\n"
        "endstream\n"
        "endobj\n"
        "5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Courier>>endobj\n"
        "xref\n"
        "0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        "0000000266 00000 n \n"
        "0000000410 00000 n \n"
        "trailer<</Size 6/Root 1 0 R>>\n"
        "startxref\n"
        "489\n"
        "%%EOF"
    )
    return pdf_content.encode("latin-1", errors="replace")


# ===== Endpoint =====

@router.get("/{report_id}/pdf", status_code=status.HTTP_200_OK)
async def download_report_pdf(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a report as PDF."""
    result = await db.execute(
        text("""
            SELECT r.id, r.topic_id, r.report_type, r.title, r.summary,
                   r.content, r.swot, r.risk_level, r.risk_items, r.opportunities,
                   r.push_time, r.status, r.feishu_doc_token, r.feishu_msg_id,
                   r.created_at, r.updated_at
            FROM reports r
            JOIN topics t ON r.topic_id = t.id
            WHERE r.id = :report_id AND t.org_id = :org_id
        """),
        {"report_id": str(report_id), "org_id": str(current_user.org_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    
    # Build report dict (same as _row_to_report)
    report_data = {
        "id": row.id,
        "topic_id": row.topic_id,
        "report_type": row.report_type,
        "title": row.title,
        "summary": row.summary,
        "content": row.content,
        "swot": row.swot,
        "risk_level": row.risk_level,
        "risk_items": row.risk_items,
        "opportunities": row.opportunities,
        "push_time": row.push_time,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    
    try:
        pdf_bytes = _generate_report_pdf(report_data)
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {str(e)[:80]}")
    
    filename = f"{row.title or 'report'}.pdf"
    # Sanitize filename to ASCII only for Content-Disposition
    ascii_filename = "".join(c if c.isascii() and c.isalnum() or c in "._- " else "_" for c in filename)
    from urllib.parse import quote
    encoded_filename = quote(filename, safe='')
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
