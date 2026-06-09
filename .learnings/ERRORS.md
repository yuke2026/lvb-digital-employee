# Errors Log

Command failures, exceptions, and unexpected behaviors encountered during development.

---

## [ERR-20260520-001] PDF export — UnicodeEncodeError in Content-Disposition

**Logged**: 2026-05-20T11:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

PDF download endpoint returned 500 with `UnicodeEncodeError: 'latin-1' codec can't encode character`.

### Error

```
UnicodeEncodeError: 'latin-1' codec can't encode character '\u62a5' in position...
```

### Context

`Content-Disposition: attachment; filename="报告.pdf"` — HTTP headers must be ASCII (latin-1). Chinese characters in the filename cause Starlette response serialization to fail.

### Suggested Fix

Use ASCII-safe `filename` + `filename*=UTF-8''URL编码` dual-header approach:

```python
from urllib.parse import quote
ascii_name = "".join(c if c.isascii() and c.isalnum() or c in "._- " else "_" for c in filename)
encoded = quote(filename, safe='')
return Response(
    headers={"Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'}
)
```

### Metadata

- Reproducible: yes
- Related Files: backend/app/api/v1/report_pdf.py
- Tags: pdf, encoding, unicode

---

## [ERR-20260520-002] PDF — SWOT content blank after fpdf2 fill rect

**Logged**: 2026-05-20T11:30:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

SWOT sections in PDF were blank (white) while file size was normal (~200KB).

### Error

SWOT text not visible — only white rectangles.

### Context

fpdf2 draws elements in call order. `rect(style="F")` called AFTER `multi_cell()` overwrote the text. The fill rectangle covered the text.

### Suggested Fix

Always draw fill BEFORE text:

```python
pdf.set_fill_color(*bg)
pdf.rect(x, y0, w, 100, style="F")  # Fill first
pdf.set_text_color(*c)
pdf.multi_cell(w, 5, text)          # Text on top
pdf.set_draw_color(*color)
pdf.rect(x, y0, w, h, style="D")    # Border only, no refill
```

### Metadata

- Reproducible: yes
- Related Files: backend/app/api/v1/report_pdf.py
- Tags: pdf, fpdf2, rendering

---

## [ERR-20260518-001] DeepSeek API 401 after model name mismatch

**Logged**: 2026-05-18T15:00:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary

Chat API returned "API key not configured" fallback. Root cause: model name was `deepseek-chat` but should be `deepseek-v4-flash`.

### Error

```
演示模式：DeepSeek API密钥未配置
```

### Context

The backend `config.py` and `.env` had `DEEPSEEK_MODEL=deepseek-chat`, which is an old model name. The actual working model is `deepseek-v4-flash`. Also, uvicorn processes started via systemd may not load `.env` unless explicitly configured (EnvironmentFile= in service file).

### Suggested Fix

```bash
# Fix model name in config
# Systemd service uses EnvironmentFile=/home/ubuntu/lvb-digital-employee/backend/.env
```

### Metadata

- Reproducible: yes (fixed now)
- Related Files: backend/app/core/config.py, backend/.env
- Tags: deepseek, api, config, model
