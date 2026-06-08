"""百应智星 · 驿递通（物流客服数字员工）API 路由

集成到百应智星数字员工平台，提供快递拦截和修改地址功能。
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.logistics.client import JTApiClient, AuthConfig, JTApiError, explain_error
from app.services.logistics.parser import (
    parse, format_intercept_response, format_modify_response, OperationType,
)
from app.services.logistics.db import db as logistics_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/logistics", tags=["驿递通·物流客服"])

# ── 延迟初始化极兔客户端 ──
_jt_client: Optional[JTApiClient] = None


def _get_jt_client() -> JTApiClient:
    """获取极兔 API 客户端（从环境变量初始化）"""
    global _jt_client
    if _jt_client is None:
        try:
            auth = AuthConfig.from_env()
            customer_code = os.environ.get("JT_CUSTOMER_CODE", "")
            _jt_client = JTApiClient(auth=auth, customer_code=customer_code)
            logger.info("驿递通 · 极兔API客户端已初始化")
        except Exception as e:
            logger.warning(f"驿递通未配置（极兔API不可用）: {e}")
            return None
    return _jt_client


# ── 模型 ──

class InterceptRequest(BaseModel):
    mail_no: str
    reason: str = "客户要求拦截退回"


class ModifyAddressRequest(BaseModel):
    txlogistic_id: str
    receiver_name: str
    receiver_mobile: str
    receiver_province: str = ""
    receiver_city: str = ""
    receiver_area: str = ""
    receiver_address: str


# ── 健康检查 ──

@router.get("/health")
async def health():
    """驿递通服务状态"""
    client = _get_jt_client()
    if client is None:
        return {"status": "not_configured", "message": "未配置极兔API凭证"}
    return {"status": "ready", "name": "驿递通·物流客服"}


# ── 拦截退回 ──

@router.post("/intercept")
async def intercept(req: InterceptRequest):
    """拦截退回"""
    client = _get_jt_client()
    if client is None:
        raise HTTPException(400, "驿递通未配置极兔API凭证")

    op_id = logistics_db.log_operation("intercept", mail_no=req.mail_no,
                                       request_params={"reason": req.reason})
    try:
        data = client.intercept(mail_no=req.mail_no, reason=req.reason)
        logistics_db.update_result(op_id, "submitted", response_data=data)
        return {"success": True, "op_id": op_id, "message": "拦截已提交", "data": data}
    except JTApiError as e:
        error_msg = explain_error(e.code)
        logistics_db.update_result(op_id, "failed", error_message=f"{e.code}: {e.message}")
        raise HTTPException(400, error_msg)


# ── 修改地址 ──

@router.post("/modify-address")
async def modify_address(req: ModifyAddressRequest):
    """修改收件地址"""
    client = _get_jt_client()
    if client is None:
        raise HTTPException(400, "驿递通未配置极兔API凭证")

    op_id = logistics_db.log_operation(
        "modify_address", txlogistic_id=req.txlogistic_id,
        request_params={
            "name": req.receiver_name, "mobile": req.receiver_mobile,
            "address": req.receiver_address,
        })
    try:
        data = client.modify_address(
            txlogistic_id=req.txlogistic_id,
            receiver_name=req.receiver_name,
            receiver_mobile=req.receiver_mobile,
            receiver_province=req.receiver_province or "广东省",
            receiver_city=req.receiver_city or "深圳市",
            receiver_area=req.receiver_area or "南山区",
            receiver_address=req.receiver_address,
        )
        logistics_db.update_result(op_id, "completed", response_data=data)
        return {
            "success": True, "op_id": op_id, "message": "地址修改成功",
            "data": {"sorting_code": data.get("sortingCode", ""), **data},
        }
    except JTApiError as e:
        error_msg = explain_error(e.code)
        logistics_db.update_result(op_id, "failed", error_message=f"{e.code}: {e.message}")
        raise HTTPException(400, error_msg)


# ── 操作记录 ──

@router.get("/operations")
async def list_operations(limit: int = 20):
    """最近操作记录"""
    return {"operations": logistics_db.get_recent(limit=limit)}


@router.get("/operations/{mail_no}")
async def get_operation(mail_no: str):
    """按运单号查询"""
    return {"operations": logistics_db.get_by_mail_no(mail_no)}


# ── 解析指令（供前端/飞书调用） ──

class ParseRequest(BaseModel):
    text: str


@router.post("/parse")
async def parse_command(req: ParseRequest):
    """解析飞书指令文本"""
    cmd = parse(req.text)
    return {
        "operation": cmd.operation.value,
        "mail_no": cmd.mail_no,
        "txlogistic_id": cmd.txlogistic_id,
        "receiver_name": cmd.receiver_name,
        "receiver_mobile": cmd.receiver_mobile,
        "receiver_address": cmd.receiver_address,
        "is_valid": cmd.is_valid,
        "confidence": cmd.confidence,
    }
