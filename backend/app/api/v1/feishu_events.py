"""
飞书 Events API Webhook 接入
处理来自飞书的事件推送（如：机器人被 @mention、消息接收、用户安装事件等）

文档: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-events/introduction
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.services.db import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["飞书事件"])


# =====================================================
# 飞书事件模型
# =====================================================

class FeishuEventHeader(BaseModel):
    """飞书事件 HTTP 头"""
    timestamp: str
    signature: str
    event_type: Optional[str] = None
    open_event_type: Optional[str] = None


class FeishuEventPayload(BaseModel):
    """飞书事件载荷基础模型"""
    schema: str = "2.0"  # noqa: N815
    header: FeishuEventHeader
    event: Optional[dict] = None


class FeishuMessageReceiveEvent(BaseModel):
    """im.message.receive_v1 事件 - 消息接收"""
    sender: dict
    recipient: dict
    message: dict
    chat_id: Optional[str] = None
    chat_type: Optional[str] = None


# =====================================================
# 安全验证
# =====================================================

def _decrypt_encrypted_content(encrypted: str, encrypt_key: str) -> str:
    """
    使用 AES/CBC 解密飞书加密内容。
    encrypt_key 为 base64 编码的 AES-256-CBC 密钥（32字节）。
    encrypted 为 base64 编码的 IV + 密文。
    """
    import base64
    import json
    from cryptography.hazmat.primitives.cipher import AES, algorithms, modes
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.backends import default_backend

    key_bytes = base64.b64decode(encrypt_key)
    encrypted_bytes = base64.b64decode(encrypted)

    # 前16字节为 IV
    iv = encrypted_bytes[:16]
    cipher_text = encrypted_bytes[16:]

    cipher = AES(key_bytes, modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(cipher_text) + decryptor.finalize()

    # PKCS7 unpadding
    pad_len = padded[-1]
    if pad_len > 16:
        raise ValueError("Invalid padding")
    unpadded = padded[:-pad_len]
    return unpadded.decode("utf-8")


def verify_feishu_signature(
    timestamp: str,
    signature: str,
    body: str,
    secret: str = settings.LARK_VERIFICATION_TOKEN,
) -> bool:
    """
    验证飞书事件签名。
    签名算法: HMAC-SHA256 + Base64(timestamp + "\n" + body, secret)
    """
    import base64
    import hmac
    import hashlib
    import time as time_module

    if not secret:
        logger.warning("[Feishu] LARK_VERIFICATION_TOKEN 未配置，跳过签名验证")
        return True

    try:
        timestamp_int = int(timestamp)
        now = int(time_module.time())
        if abs(now - timestamp_int) > 60 * 5:  # 5分钟内
            logger.warning(f"[Feishu] 事件时间戳过期: {timestamp}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"[Feishu] 无效时间戳: {timestamp}")
        return False

    string_to_sign = f"{timestamp}\n{body}"
    hmac_obj = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    )
    computed = base64.b64encode(hmac_obj.digest()).decode("utf-8")
    return hmac.compare_digest(computed, signature)


# =====================================================
# 事件处理
# =====================================================

async def _handle_message_receive(event_data: dict) -> dict:
    """
    处理 im.message.receive_v1 事件。
    当用户 @机器人 发送消息时，触发 AI 对话流程。
    """
    message = event_data.get("message", {})
    sender = event_data.get("sender", {})
    chat_id = event_data.get("chat_id")
    chat_type = event_data.get("chat_type", "")

    # 只处理 group 类型的消息（@机器人）
    if chat_type != "group":
        logger.info(f"[Feishu] 忽略非群聊消息: chat_type={chat_type}")
        return {"code": 0, "msg": "ignored"}

    message_type = message.get("message_type")
    if message_type != "text":
        logger.info(f"[Feishu] 忽略非文本消息: type={message_type}")
        return {"code": 0, "msg": "ignored"}

    # 提取文本内容
    content = message.get("content", "{}")
    try:
        content_obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        content_obj = {}

    text = content_obj.get("text", "").strip()
    if not text:
        return {"code": 0, "msg": "empty"}

    message_id = message.get("message_id")
    open_id = sender.get("open_id")

    logger.info(
        f"[Feishu] 收到群消息: chat_id={chat_id}, open_id={open_id}, "
        f"message_id={message_id}, text={text[:50]}"
    )

    # 检查是否为 @机器人 的消息
    mentions = message.get("mentions", [])
    if not any(ment.get("key", "").startswith("@_user_") or "_user_" in str(ment) for ment in mentions):
        # 检查消息是否以 @ 开头
        if not text.startswith("@"):
            logger.info(f"[Feishu] 非 @ 消息，跳过: {text[:30]}")
            return {"code": 0, "msg": "not_mentioned"}

    # 去掉 @ 提及前缀
    clean_text = text
    for ment in mentions:
        key = ment.get("key", "")
        if key.startswith("@"):
            clean_text = clean_text.replace(key, "").strip()

    # 查找该 chat_id 对应的数字员工对话
    # 逻辑：取该 chat_id 最近一次活跃的对话
    # TODO: 后续可改为 chat_id + employee_id 映射表
    try:
        from app.services.ai import chat_with_deepseek_stream
        from app.services.db import db

        # 查找企业内任意一个活跃数字员工（简化处理）
        employees = db.list_employees()
        if not employees:
            logger.warning("[Feishu] 无可用数字员工")
            return {"code": 0, "msg": "no_employee"}

        employee = employees[0]

        # 构建对话上下文
        messages = [{"role": "user", "content": clean_text}]

        # 调用 AI 流式生成回复
        reply_parts = []
        async for chunk in chat_with_deepseek_stream(
            system_prompt=employee.system_prompt,
            messages=messages,
        ):
            reply_parts.append(chunk)

        full_reply = "".join(reply_parts)
        if full_reply:
            # 通过飞书 IM API 发送回复到群
            from app.services.feishu_chat_push import FeishuChatClient
            feishu_client = FeishuChatClient()
            await feishu_client.send_text_message(
                receive_id_type="chat_id",
                receive_id=chat_id,
                content=json.dumps({"text": full_reply}),
            )
            logger.info(f"[Feishu] 已回复群消息: chat_id={chat_id}, reply_len={len(full_reply)}")
        return {"code": 0, "msg": "processed"}
    except Exception as e:
        logger.error(f"[Feishu] 处理消息异常: {e}", exc_info=True)
        return {"code": 1, "msg": str(e)}


# =====================================================
# Webhook 端点
# =====================================================

@router.post("/webhook/feishu")
async def feishu_webhook(
    request: Request,
    x_feishu_timestamp: str = Header(None, alias="X-Feishu-Timestamp"),
    x_feishu_signature: str = Header(None, alias="X-Feishu-Signature"),
):
    """
    飞书事件 Webhook 接收端点。

    飞书 POST 请求时：
    1. 验证签名（若配置了 LARK_VERIFICATION_TOKEN）
    2. 若是 url_verification 事件（事件配置时验证），直接返回 challenge
    3. 若已加密，解密后再处理
    4. 根据 event_type 分发到对应 handler
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    # ── 1. URL 验证事件（飞书配置事件订阅时发送）─────────────
    try:
        body_json = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # 飞书事件挑战验证
    if body_json.get("type") == "url_verification":
        challenge = body_json.get("challenge", "")
        logger.info("[Feishu] URL 验证请求，返回 challenge")
        return {"code": 0, "challenge": challenge}

    # ── 2. 签名验证 ─────────────────────────────────────────
    if settings.LARK_VERIFICATION_TOKEN and x_feishu_signature:
        if not verify_feishu_signature(
            x_feishu_timestamp or "",
            x_feishu_signature,
            body_str,
        ):
            logger.warning("[Feishu] 签名验证失败")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # ── 3. 事件分发 ─────────────────────────────────────────
    header = body_json.get("header", {})
    event_type = header.get("event_type") or header.get("open_event_type", "")

    logger.info(f"[Feishu] 收到事件: event_type={event_type}")

    # 解密处理（若飞书配置了加密）
    event = body_json.get("event", {})
    if body_json.get("encrypt"):
        try:
            decrypted = _decrypt_encrypted_content(
                body_json["encrypt"],
                settings.LARK_ENCRYPT_KEY,
            )
            event = json.loads(decrypted).get("event", {})
        except Exception as e:
            logger.error(f"[Feishu] 解密失败: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decryption failed")

    # 事件处理
    if event_type == "im.message.receive_v1":
        result = await _handle_message_receive(event)
    else:
        logger.info(f"[Feishu] 未知事件类型: {event_type}，跳过")
        result = {"code": 0, "msg": "unknown_event"}

    return result


@router.get("/webhook/feishu")
async def feishu_webhook_get():
    """
    飞书配置 URL 验证（GET 请求）。
    直接返回 200 OK 表示服务可用。
    """
    return {"status": "ok", "service": "feishu-events"}
