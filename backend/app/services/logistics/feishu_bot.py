"""驿递通 · 飞书消息收发工具"""
import os
import json
import logging
from typing import Optional

import requests

logger = logging.getLogger("驿递通.feishu")

# 飞书开放平台 API
FEISHU_BASE = "https://open.feishu.cn/open-apis"


class FeishuBot:
    """飞书自建应用机器人"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._tenant_token: Optional[str] = None
        self._token_expires: int = 0

    # ── 获取 tenant_access_token ──

    def _get_token(self) -> str:
        """获取/刷新 tenant_access_token"""
        import time
        now = int(time.time())
        if self._tenant_token and now < self._token_expires - 60:
            return self._tenant_token

        resp = requests.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 token 获取失败: {data.get('msg', '')}")

        self._tenant_token = data["tenant_access_token"]
        self._token_expires = now + data.get("expire", 7200)
        logger.info("[飞书] tenant_access_token 已刷新")
        return self._tenant_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ── 发送消息到群聊 ──

    def send_group_message(self, chat_id: str, text: str) -> bool:
        """发送文本消息到飞书群

        Args:
            chat_id: 飞书群聊的 chat_id
            text: 消息文本（支持 Markdown 格式）
        """
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }

        resp = requests.post(
            f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id",
            headers=self._headers(),
            json=body,
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"[飞书] 发送消息失败: {data.get('msg', '')} ({data.get('code')})")
            return False

        logger.info(f"[飞书] 消息已发送到群 {chat_id[:12]}...")
        return True

    def send_interactive_message(self, chat_id: str, title: str,
                                 content_lines: list) -> bool:
        """发送富文本交互消息（卡片消息）"""
        elements = []
        for line in content_lines:
            if line.startswith("---"):
                elements.append({"tag": "hr"})
            elif line.startswith("**") and line.endswith("**"):
                elements.append({
                    "tag": "markdown",
                    "content": line.strip("*"),
                    "style": {"bold": True},
                })
            else:
                elements.append({
                    "tag": "markdown",
                    "content": line,
                })

        body = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps({
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "green" if "成功" in title or "完成" in title else "red",
                },
                "elements": elements,
            }, ensure_ascii=False),
        }

        resp = requests.post(
            f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id",
            headers=self._headers(),
            json=body,
            timeout=10,
        )
        data = resp.json()
        return data.get("code") == 0

    # ── 验证飞书事件回调签名 ──

    @staticmethod
    def verify_event(body: dict, verification_token: str) -> bool:
        """验证飞书事件回调"""
        token = body.get("token", "") if isinstance(body, dict) else ""
        return token == verification_token

    @staticmethod
    def load_from_env():
        """从环境变量加载飞书配置"""
        return FeishuBot(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
        )
