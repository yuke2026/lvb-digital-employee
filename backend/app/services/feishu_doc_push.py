"""飞书文档推送服务 - 将报告内容推送到飞书文档"""
import json
import logging
from typing import Optional
from datetime import datetime

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class FeishuDocClient:
    """飞书文档 API 客户端"""

    def __init__(self):
        self.app_id = settings.LARK_APP_ID
        self.app_secret = settings.LARK_APP_SECRET
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _get_token(self) -> str:
        """获取 tenant_access_token，缓存于实例级别"""
        if self._tenant_access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return self._tenant_access_token

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书获取token失败: {data}")
            self._tenant_access_token = data["tenant_access_token"]
            # token 有效期 2 小时，提前 5 分钟刷新
            self._token_expires_at = datetime.utcnow().replace(microsecond=0)
            from datetime import timedelta
            self._token_expires_at += timedelta(hours=2, minutes=-5)
            return self._tenant_access_token

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def create_document(self, title: str) -> str:
        """创建空白飞书文档，返回 doc_token"""
        token = await self._get_token()
        url = f"{self.base_url}/docx/v1/documents"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers=self._headers(token),
                json={"title": title},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书创建文档失败: {data}")
            return data["data"]["document"]["document_id"]

    async def create_folder(self, name: str, parent_token: str = "") -> str:
        """在指定文件夹下创建新文件夹，返回 folder_token"""
        token = await self._get_token()
        url = f"{self.base_url}/drive/v1/files/create_folder"
        payload = {"name": name, "parent_token": parent_token}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers=self._headers(token),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书创建文件夹失败: {data}")
            return data["data"]["token"]

    async def batch_update_document(
        self,
        doc_token: str,
        blocks: list[dict],
    ) -> dict:
        """批量在文档中插入/更新内容块（原子更新）"""
        token = await self._get_token()
        url = f"{self.base_url}/docx/v1/documents/{doc_token}/blocks/batchUpdate"
        payload = {
            "requests": [
                {
                    "update_blocks": {
                        "blocks": blocks,
                        "style": {},
                    }
                }
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.patch(
                url,
                headers=self._headers(token),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()


def _make_text_block(
    text: str,
    bold: bool = False,
    level: int = 1,
) -> dict:
    """生成飞书文本块
    level: 1=普通文本, 2=标题2, 3=标题3
    """
    tag_map = {1: "text", 2: "heading2", 3: "heading3"}
    tag = tag_map.get(level, "text")
    block_tag = f"block-{tag}"
    text_style = {"bold": bold} if bold else {}
    return {
        "block_type": 2,  # TextBlock
        block_tag: {
            "elements": [{"text_run": {"content": text, "text_element_style": text_style}}],
            "style": {},
        },
    }


def _make_ordered_list_block(items: list[str]) -> list[dict]:
    """生成有序列表块"""
    blocks = []
    for item in items:
        blocks.append({
            "block_type": 12,  # Ordered
            "block_ordered": {
                "elements": [{"text_run": {"content": item, "text_element_style": {}}}],
                "style": {},
            },
        })
    return blocks


def _make_unordered_list_block(items: list[str]) -> list[dict]:
    """生成无序列表块"""
    blocks = []
    for item in items:
        blocks.append({
            "block_type": 13,  # Unordered
            "block_unordered": {
                "elements": [{"text_run": {"content": item, "text_element_style": {}}}],
                "style": {},
            },
        })
    return blocks


def _make_divider_block() -> dict:
    return {"block_type": 4, "block_divider": {"style": {"divider_color": 1}}}


def _swot_to_blocks(swot: dict) -> list[dict]:
    """将 SWOT 字典转换为飞书块列表"""
    blocks = []
    quadrants = [
        ("strengths", "💪 优势 Strengths", swot.get("strengths", [])),
        ("weaknesses", "⚠️ 劣势 Weaknesses", swot.get("weaknesses", [])),
        ("opportunities", "🚀 机会 Opportunities", swot.get("opportunities", [])),
        ("threats", "🚨 威胁 Threats", swot.get("threats", [])),
    ]
    for key, title, items in quadrants:
        blocks.append(_make_text_block(title, bold=True, level=2))
        if items:
            if isinstance(items, list):
                blocks.extend(_make_unordered_list_block(items))
            else:
                blocks.append(_make_text_block(str(items)))
        else:
            blocks.append(_make_text_block("（暂无数据）"))
        blocks.append(_make_divider_block())
    return blocks


def _risk_items_to_blocks(risk_items: dict) -> list[dict]:
    """将风险项转换为飞书块"""
    blocks = []
    blocks.append(_make_text_block("🔎 风险分析 Risk Analysis", bold=True, level=2))
    if not risk_items:
        blocks.append(_make_text_block("（暂无数据）"))
        return blocks

    risk_colors = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    for category, risks in risk_items.items():
        cat_label = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}.get(
            category, category
        )
        blocks.append(_make_text_block(cat_label, bold=True, level=3))
        if isinstance(risks, list):
            blocks.extend(_make_unordered_list_block(risks))
        else:
            blocks.append(_make_text_block(str(risks)))
    return blocks


def report_to_feishu_blocks(report_data: dict) -> list[dict]:
    """将完整报告数据转换为飞书文档块列表"""
    blocks = []

    # 标题
    blocks.append(_make_text_block(report_data.get("title", "战略分析报告"), level=1))
    blocks.append(_make_divider_block())

    # 元信息
    meta_lines = []
    if report_data.get("report_type"):
        type_map = {"daily": "📅 日报", "weekly": "📆 周报", "monthly": "📊 月报"}
        meta_lines.append(type_map.get(report_data["report_type"], report_data["report_type"]))
    if report_data.get("summary"):
        meta_lines.append(f"📝 摘要：{report_data['summary']}")
    if report_data.get("risk_level"):
        level_map = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}
        meta_lines.append(f"⚡ 风险等级：{level_map.get(report_data['risk_level'], report_data['risk_level'])}")
    if meta_lines:
        blocks.append(_make_text_block(" | ".join(meta_lines)))
        blocks.append(_make_divider_block())

    # SWOT
    swot = report_data.get("swot", {})
    if swot:
        blocks.extend(_swot_to_blocks(swot))

    # 风险项
    risk_items = report_data.get("risk_items", {})
    if risk_items:
        blocks.extend(_risk_items_to_blocks(risk_items))

    # 机会
    opportunities = report_data.get("opportunities", {})
    if opportunities:
        blocks.append(_make_text_block("💡 商业机会 Business Opportunities", bold=True, level=2))
        if isinstance(opportunities, list):
            blocks.extend(_make_unordered_list_block(opportunities))
        else:
            blocks.append(_make_text_block(str(opportunities)))
        blocks.append(_make_divider_block())

    return blocks


async def push_report_to_feishu(
    report_data: dict,
    feishu_folder_token: str = "",
) -> tuple[str, str]:
    """
    将报告推送到飞书文档。

    Returns:
        (doc_token, doc_url)
    """
    client = FeishuDocClient()

    # 生成文档标题
    title = report_data.get("title", "战略分析报告")
    if report_data.get("report_type"):
        type_map = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
        suffix = type_map.get(report_data["report_type"], "")
        title = f"{title} - {suffix}" if suffix else title

    # 1. 创建文档
    doc_token = await client.create_document(title)

    # 2. 构建块内容
    blocks = report_to_feishu_blocks(report_data)

    # 3. 写入内容
    if blocks:
        await client.batch_update_document(doc_token, blocks)

    doc_url = f"https://bytedance.feishu.cn/docx/{doc_token}"
    logger.info(f"飞书文档已创建: {doc_url}")
    return doc_token, doc_url


async def push_report_to_feishu_with_retry(
    report_data: dict,
    feishu_folder_token: str = "",
    max_retries: int = 3,
) -> tuple[str, str]:
    """带重试的飞书文档推送"""
    for attempt in range(max_retries):
        try:
            return await push_report_to_feishu(report_data, feishu_folder_token)
        except Exception as e:
            logger.warning(f"飞书推送失败（尝试 {attempt + 1}/{max_retries}）: {e}")
            if attempt == max_retries - 1:
                raise
            import asyncio
            await asyncio.sleep(2 ** attempt)
