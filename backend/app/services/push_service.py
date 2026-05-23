"""推送服务 - 整合飞书文档推送、飞书消息推送和推送记录"""
import uuid
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feishu_doc_push import push_report_to_feishu_with_retry
from app.services.feishu_chat_push import FeishuChatClient, build_report_push_content

logger = logging.getLogger(__name__)


async def record_push(
    db: AsyncSession,
    report_id: UUID,
    channel: str,
    recipient: str,
    status: str,
    sent_at: Optional[datetime] = None,
    error_msg: Optional[str] = None,
) -> UUID:
    """将推送记录写入 push_records 表"""
    now = datetime.utcnow()
    result = await db.execute(
        text("""
            INSERT INTO push_records (id, report_id, channel, recipient, status, sent_at, error_msg, created_at)
            VALUES (:id, :report_id, :channel, :recipient, :status, :sent_at, :error_msg, :created_at)
            RETURNING id
        """),
        {
            "id": str(uuid.uuid4()),
            "report_id": str(report_id),
            "channel": channel,
            "recipient": recipient,
            "status": status,
            "sent_at": sent_at or now,
            "error_msg": error_msg,
            "created_at": now,
        },
    )
    await db.commit()
    row = result.fetchone()
    return row[0] if row else None


async def push_report_full(
    report_id: UUID,
    report_data: dict,
    feishu_chat_id: Optional[str] = None,
    feishu_open_ids: Optional[list[str]] = None,
) -> dict:
    """
    执行报告的完整推送流程：
    1. 推送到飞书文档
    2. 推送飞书消息（可选）
    3. 记录推送结果

    Returns:
        dict with doc_token, doc_url, feishu_msg_ids
    """
    results = {
        "feishu_doc_token": None,
        "feishu_doc_url": None,
        "feishu_msg_ids": [],
        "errors": [],
    }

    # 如果 feishu 凭证未配置，跳过飞书相关推送
    from app.core.config import settings
    feishu_enabled = bool(settings.LARK_APP_ID and settings.LARK_APP_SECRET)

    if feishu_enabled:
        # Step 1: 飞书文档
        try:
            doc_token, doc_url = await push_report_to_feishu_with_retry(report_data)
            results["feishu_doc_token"] = doc_token
            results["feishu_doc_url"] = doc_url
            logger.info(f"飞书文档推送成功: {doc_url}")
        except Exception as e:
            results["errors"].append(f"飞书文档: {e}")
            logger.error(f"飞书文档推送失败: {e}", exc_info=True)

        # Step 2: 飞书消息
        if feishu_chat_id or feishu_open_ids:
            chat_client = FeishuChatClient()
            doc_url = results["feishu_doc_url"]

            # 发送到群
            if feishu_chat_id:
                try:
                    resp = await chat_client.send_report_card(
                        receive_id_type="chat_id",
                        receive_id=feishu_chat_id,
                        report=report_data,
                        doc_url=doc_url,
                    )
                    msg_id = resp.get("data", {}).get("message_id")
                    results["feishu_msg_ids"].append(msg_id)
                    logger.info(f"飞书群消息发送成功: {msg_id}")
                except Exception as e:
                    results["errors"].append(f"飞书群消息: {e}")
                    logger.warning(f"飞ign群消息发送失败: {e}")

            # 发送到个人
            if feishu_open_ids:
                for open_id in feishu_open_ids:
                    try:
                        resp = await chat_client.send_report_card(
                            receive_id_type="open_id",
                            receive_id=open_id,
                            report=report_data,
                            doc_url=doc_url,
                        )
                        msg_id = resp.get("data", {}).get("message_id")
                        results["feishu_msg_ids"].append(msg_id)
                        logger.info(f"飞书私聊消息发送成功: {msg_id}")
                    except Exception as e:
                        results["errors"].append(f"飞书私聊({open_id}): {e}")
                        logger.warning(f"飞书私聊消息发送失败: {e}")
    else:
        logger.info("飞书凭证未配置，跳过飞书推送")

    return results


async def push_report_full_with_db(
    db: AsyncSession,
    report_id: UUID,
    report_data: dict,
    feishu_chat_id: Optional[str] = None,
    feishu_open_ids: Optional[list[str]] = None,
) -> dict:
    """
    执行完整推送流程并记录到数据库。
    自动更新 reports 表的 feishu_doc_token 和 feishu_msg_id 字段。
    """
    results = await push_report_full(
        report_id=report_id,
        report_data=report_data,
        feishu_chat_id=feishu_chat_id,
        feishu_open_ids=feishu_open_ids,
    )

    # 更新报告的飞书字段
    if results["feishu_doc_token"]:
        await db.execute(
            text("""
                UPDATE reports
                SET feishu_doc_token = :doc_token,
                    feishu_msg_id = :msg_id,
                    updated_at = :updated_at
                WHERE id = :report_id
            """),
            {
                "doc_token": results["feishu_doc_token"],
                "msg_id": results["feishu_msg_ids"][0] if results["feishu_msg_ids"] else None,
                "updated_at": datetime.utcnow(),
                "report_id": str(report_id),
            },
        )
        await db.commit()

    # 记录推送记录
    if results["feishu_doc_token"]:
        await record_push(
            db=db,
            report_id=report_id,
            channel="feishu_doc",
            recipient=results["feishu_doc_token"],
            status="success" if not results["errors"] else "partial",
            error_msg="; ".join(results["errors"]) if results["errors"] else None,
        )

    return results
