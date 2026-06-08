"""驿递通 · 数据模型"""
from pydantic import BaseModel, Field
from typing import Optional


class InterceptRequest(BaseModel):
    """拦截请求"""
    mail_no: str
    reason: str = "客户要求拦截退回"


class ModifyAddressRequest(BaseModel):
    """修改地址请求"""
    txlogistic_id: str
    receiver_name: str
    receiver_mobile: str
    receiver_province: str = ""
    receiver_city: str = ""
    receiver_area: str = ""
    receiver_address: str


class OperationResponse(BaseModel):
    """操作结果"""
    success: bool
    operation: str
    message: str
    data: Optional[dict] = None
    op_id: Optional[int] = None


class CallbackPayload(BaseModel):
    """极兔拦截回传回调"""
    mailNo: Optional[str] = None
    billCode: Optional[str] = None
    interceptResult: Optional[str] = None
    returnMailNo: Optional[str] = None
    feedbackTime: Optional[str] = None


class FeishuEvent(BaseModel):
    """飞书事件回调"""
    token: Optional[str] = None
    challenge: Optional[str] = None
    type: Optional[str] = None
    event: Optional[dict] = None
    event_schema: Optional[str] = Field(None, alias="schema")
    header: Optional[dict] = None
