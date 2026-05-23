"""飞书聊天推送服务 - 推送报告摘要到飞书群或私聊"""
import logging
from typing import Optional

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class FeishuChatClient:
    """飞书 IM（即时通讯）API 客户端 - 用于推送消息到群/私聊"""

    def __init__(self):
        self.app_id = settings.LARK_APP_ID
        self.app_secret = settings.LARK_APP_SECRET
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_access_token: Optional[str] = None

    async def _get_token(self) -> str:
        """获取 tenant_access_token"""
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
            return data["tenant_access_token"]

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _do_post(self, url: str, token: str, payload: dict) -> dict:
        """POST helper with token auto-refresh"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._headers(token), json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书API错误: {data}")
            return data

    async def send_text_message(self, receive_id_type: str, receive_id: str, content: str) -> dict:
        """
        发送文本消息到指定接收者。

        Args:
            receive_id_type: "chat_id"（群ID）或 "open_id" / "user_id"（个人）
            receive_id: 接收者ID
            content: 文本内容（JSON字符串）
        """
        token = await self._get_token()
        url = f"{self.base_url}/im/v1/messages"
        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "text",
            "content": content,  # {"text": "内容"}
        }
        return await self._do_post(url, token, payload)

    async def send_rich_text_message(
        self,
        receive_id_type: str,
        receive_id: str,
        title: str,
        content_lines: list[str],
    ) -> dict:
        """
        发送富文本消息（卡片样式）到指定接收者。

        使用飞书 "post" 消息类型，支持多行富文本。
        """
        token = await self._get_token()
        url = f"{self.base_url}/im/v1/messages"

        # 构建 post 消息的 content
        content = {
            "zh_cn": {
                "title": title,
                "content": [
                    # 每行是一个 paragraph，包含多个 text Run
                    [
                        {
                            "tag": "text",
                            "text": line,
                        }
                    ]
                    for line in content_lines
                ],
            }
        }

        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "post",
            "content": content,
        }
        return await self._do_post(url, token, payload)

    async def send_report_card(
        self,
        receive_id_type: str,
        receive_id: str,
        report: dict,
        doc_url: Optional[str] = None,
    ) -> dict:
        """
        发送报告摘要卡片消息。

        包含：报告类型标签 + 标题 + 摘要 + 风险等级 + 一句话摘要 + 飞书文档链接按钮。
        """
        token = await self._get_token()
        url = f"{self.base_url}/im/v1/messages"

        type_map = {"daily": "📅 日报", "weekly": "📆 周报", "monthly": "📊 月报"}
        risk_map = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}

        report_type_label = type_map.get(report.get("report_type", ""), report.get("report_type", "报告"))
        risk_label = risk_map.get(report.get("risk_level", ""), "")

        title = report.get("title", "战略分析报告")
        summary = report.get("summary", "暂无摘要")

        # 飞书 post 消息的 content
        content_parts = [
            [{"tag": "text", "text": f"{report_type_label} · {risk_label}"}],
            [{"tag": "text", "text": title, "text_style": {"bold": True}}],
            [{"tag": "text", "text": summary}],
        ]

        # 添加关键发现（如果有）
        if report.get("swot"):
            swot = report["swot"]
            if swot.get("strengths") and isinstance(swot["strengths"], list) and swot["strengths"]:
                top = swot["strengths"][0] if swot["strengths"] else ""
                if top:
                    content_parts.append([{"tag": "text", "text": f"💪 核心优势: {top}"}])
            if swot.get("threats") and isinstance(swot["threats"], list) and swot["threats"]:
                top = swot["threats"][0] if swot["threats"] else ""
                if top:
                    content_parts.append([{"tag": "text", "text": f"🚨 首要威胁: {top}"}])

        content = {"zh_cn": {"title": title, "content": content_parts}}

        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": "post",
            "content": content,
        }
        result = await self._do_post(url, token, payload)

        # 如果提供了 doc_url，单独再发一条带按钮的消息
        if doc_url:
            btn_payload = {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "msg_type": "interactive",
                "content": {
                    "zh_cn": {
                        "title": title,
                        "content": {
                            "elements": [
                                {
                                    "tag": "action",
                                    "actions": [
                                        {
                                            "tag": "button",
                                            "text": {"tag": "plain_text", "text": "📄 查看完整报告"},
                                            "type": "primary",
                                            "url": doc_url,
                                        }
                                    ],
                                }
                            ],
                            "params": {"width": 400},
                        },
                    }
                },
            }
            try:
                await self._do_post(url, token, btn_payload)
            except Exception as e:
                logger.warning(f"飞书按钮消息发送失败（非致命）: {e}")

        return result


def build_report_push_content(report: dict, doc_url: Optional[str] = None) -> dict:
    """
    构建报告推送内容（供其他渠道复用，如 email / webhook）。
    返回包含 title/summary/risk_level/doc_url 的字典。
    """
    return {
        "title": report.get("title", "战略分析报告"),
        "summary": report.get("summary", ""),
        "risk_level": report.get("risk_level"),
        "report_type": report.get("report_type"),
        "doc_url": doc_url or f"https://bytedance.feishu.cn/docx/{report.get('feishu_doc_token', '')}",
        "swot": report.get("swot", {}),
        "risk_items": report.get("risk_items", {}),
    }
