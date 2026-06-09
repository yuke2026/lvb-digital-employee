"""百应智星 · 驿递通（物流客服数字员工）API 路由

集成到百应智星数字员工平台，提供快递拦截和修改地址功能。
支持 SaaS 多租户：每家企业可在前端自助配置极兔API凭证。
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.plugin_config import PluginConfig
from app.services.logistics.client import JTApiClient, AuthConfig, JTApiError, explain_error
from app.services.logistics.parser import (
    parse, format_intercept_response, format_modify_response, OperationType,
)
from app.services.logistics.db import db as logistics_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/logistics", tags=["驿递通·物流客服"])

PLUGIN_NAME = "logistics"


# ── Helpers ──

async def _get_org_id(db_session: AsyncSession, user: User) -> str:
    """获取当前用户所属企业 ID"""
    if not user.org_id:
        raise HTTPException(400, "当前用户未关联企业账号")
    return str(user.org_id)


async def _get_plugin_config(db_session: AsyncSession, org_id: str) -> dict:
    """获取企业物流插件配置"""
    result = await db_session.execute(
        select(PluginConfig).where(
            PluginConfig.org_id == org_id,
            PluginConfig.plugin == PLUGIN_NAME,
        )
    )
    pc = result.scalar_one_or_none()
    if pc:
        return pc.get_config_dict()
    return {}


async def _save_plugin_config(db_session: AsyncSession, org_id: str, config_dict: dict):
    """保存企业物流插件配置"""
    result = await db_session.execute(
        select(PluginConfig).where(
            PluginConfig.org_id == org_id,
            PluginConfig.plugin == PLUGIN_NAME,
        )
    )
    pc = result.scalar_one_or_none()
    if pc:
        pc.config = json.dumps(config_dict, ensure_ascii=False)
    else:
        pc = PluginConfig(
            org_id=org_id,
            plugin=PLUGIN_NAME,
            config=json.dumps(config_dict, ensure_ascii=False),
        )
        db_session.add(pc)


def _build_client_from_config(plugin_cfg: dict) -> Optional[JTApiClient]:
    """从插件配置构建极兔 API 客户端"""
    auth = AuthConfig.from_dict(plugin_cfg)
    if not auth.is_valid():
        return None
    customer_code = plugin_cfg.get("customer_code", "")
    return JTApiClient(auth=auth, customer_code=customer_code)


# ── 模型 ──

class LogisticsConfig(BaseModel):
    """物流插件配置"""
    api_account: str = ""
    plain_password: str = ""
    private_key: str = ""
    customer_code: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_chat_id: str = ""


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


# ═══════════════════════════════════════════════════════
# 配置管理（SaaS 多租户）
# ═══════════════════════════════════════════════════════

@router.get("/config")
async def get_config(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """获取当前企业的物流配置（返回时隐藏敏感字段）"""
    org_id = await _get_org_id(db_session, current_user)
    plugin_cfg = await _get_plugin_config(db_session, org_id)

    def mask(s: str) -> str:
        if len(s) <= 4:
            return s[:1] + "***" if s else ""
        return s[:2] + "****" + s[-2:]

    return LogisticsConfig(
        api_account=mask(plugin_cfg.get("api_account", "")),
        plain_password=mask(plugin_cfg.get("plain_password", "")),
        private_key=mask(plugin_cfg.get("private_key", "")),
        customer_code=plugin_cfg.get("customer_code", ""),
        feishu_app_id=mask(plugin_cfg.get("feishu_app_id", "")),
        feishu_app_secret=mask(plugin_cfg.get("feishu_app_secret", "")),
        feishu_chat_id=plugin_cfg.get("feishu_chat_id", ""),
    )


@router.put("/config")
async def update_config(
    cfg: LogisticsConfig,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """更新当前企业的物流配置"""
    org_id = await _get_org_id(db_session, current_user)

    existing = await _get_plugin_config(db_session, org_id)
    new_cfg = {**existing}
    for key in ("api_account", "plain_password", "private_key",
                "customer_code", "feishu_app_id", "feishu_app_secret", "feishu_chat_id"):
        val = getattr(cfg, key, None)
        if val:
            new_cfg[key] = val

    await _save_plugin_config(db_session, org_id, new_cfg)
    await db_session.commit()
    return {"success": True, "message": "物流配置已保存"}


@router.post("/test-connection")
async def test_connection(
    cfg: LogisticsConfig,
    current_user: User = Depends(get_current_user),
):
    """测试极兔API连接（用提供的配置测试，不会保存）"""
    auth = AuthConfig.from_dict({
        "api_account": cfg.api_account,
        "plain_password": cfg.plain_password,
        "private_key": cfg.private_key,
    })
    if not auth.is_valid():
        raise HTTPException(400, "极兔API凭证不完整，请填写 api_account / plain_password / private_key")

    try:
        client = JTApiClient(auth=auth, customer_code=cfg.customer_code)
        result = client.test_connection()
        return {"success": True, "message": "连接成功 ✅", "data": result}
    except JTApiError as e:
        error_msg = explain_error(e.code)
        return {"success": False, "message": f"连接失败: {error_msg} ({e.code})"}
    except Exception as e:
        return {"success": False, "message": f"连接异常: {str(e)}"}


@router.post("/test-feishu")
async def test_feishu_connection(
    cfg: LogisticsConfig,
    current_user: User = Depends(get_current_user),
):
    """测试飞书机器人连接（用提供的配置获取 tenant access token）"""
    if not cfg.feishu_app_id or not cfg.feishu_app_secret:
        raise HTTPException(400, "请填写 App ID 和 App Secret")

    try:
        import httpx
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": cfg.feishu_app_id, "app_secret": cfg.feishu_app_secret},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            msg = "飞书连接成功"
            if cfg.feishu_chat_id:
                msg += f"，群聊 chat_id: {cfg.feishu_chat_id}"
            return {"success": True, "message": msg}
        else:
            return {"success": False, "message": f"飞书认证失败: {data.get('msg', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"连接异常: {str(e)}"}


# ═══════════════════════════════════════════════════════
# 业务操作
# ═══════════════════════════════════════════════════════

async def _get_client_for_org(db_session, user) -> JTApiClient:
    """获取当前企业配置的极兔客户端"""
    org_id = await _get_org_id(db_session, user)
    plugin_cfg = await _get_plugin_config(db_session, org_id)
    client = _build_client_from_config(plugin_cfg)
    if client is None:
        raise HTTPException(400, "物流客服尚未配置，请先在设置中填写极兔API凭证")
    return client


@router.get("/health")
async def health(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """驿递通服务状态"""
    try:
        org_id = await _get_org_id(db_session, current_user)
        plugin_cfg = await _get_plugin_config(db_session, org_id)
        auth = AuthConfig.from_dict(plugin_cfg)
        if not auth.is_valid():
            return {"status": "not_configured", "name": "驿递通·物流客服",
                    "message": "未配置极兔API凭证，请在设置中配置"}
        return {"status": "ready", "name": "驿递通·物流客服",
                "message": "已配置，等待操作指令"}
    except HTTPException:
        return {"status": "not_configured", "message": "物流客服尚未配置"}


@router.post("/intercept")
async def intercept(
    req: InterceptRequest,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """拦截退回"""
    client = await _get_client_for_org(db_session, current_user)

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


@router.post("/modify-address")
async def modify_address(
    req: ModifyAddressRequest,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """修改收件地址"""
    client = await _get_client_for_org(db_session, current_user)

    op_id = logistics_db.log_operation(
        "modify_address", txlogistic_id=req.txlogistic_id,
        request_params={"name": req.receiver_name, "mobile": req.receiver_mobile,
                        "address": req.receiver_address})
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
        return {"success": True, "op_id": op_id, "message": "地址修改成功",
                "data": {"sorting_code": data.get("sortingCode", ""), **data}}
    except JTApiError as e:
        error_msg = explain_error(e.code)
        logistics_db.update_result(op_id, "failed", error_message=f"{e.code}: {e.message}")
        raise HTTPException(400, error_msg)


@router.get("/operations")
async def list_operations(limit: int = 20):
    """最近操作记录"""
    return {"operations": logistics_db.get_recent(limit=limit)}


@router.get("/operations/{mail_no}")
async def get_operation(mail_no: str):
    """按运单号查询"""
    return {"operations": logistics_db.get_by_mail_no(mail_no)}


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
