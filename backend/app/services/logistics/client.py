"""驿递通 · 极兔速递 API 客户端

三层签名算法（从开放平台 JS 文档提取）：
  1. 密文 = MD5(明文密码 + "jadada236t2").toUpperCase()
  2. bodyDigest = Base64(MD5(客户编号 + 密文 + privateKey))
  3. Header: apiAccount + bodyDigest + timestamp
  4. Body: bizContent = JSON.stringify(业务参数)

API 端点：
  - 拦截下发: /other/intercept
  - 创建/修改订单: /orderserve/create
  - 拦截回传(回调): /other/interceptFeedback
"""

import hashlib
import base64
import json
import time
import logging
from typing import Optional
from datetime import datetime

import requests

logger = logging.getLogger("驿递通.jtexpress")

# ── 常量 ──
SALT = "jadada236t2"  # 从官方 JS 文档提取的固定盐值
API_BASE = "https://openapi.jtexpress.com.cn"


# ═══════════════════════════════════════════════════════════
# 签名工具
# ═══════════════════════════════════════════════════════════

class AuthConfig:
    """极兔 API 认证配置"""

    def __init__(self, api_account: str, plain_password: str, private_key: str):
        self.api_account = api_account
        self.plain_password = plain_password
        self.private_key = private_key

    @classmethod
    def from_env(cls):
        """从环境变量加载（兼容旧模式）"""
        import os
        return cls(
            api_account=os.environ["JT_API_ACCOUNT"],
            plain_password=os.environ["JT_PLAIN_PASSWORD"],
            private_key=os.environ["JT_PRIVATE_KEY"],
        )

    @classmethod
    def from_dict(cls, config: dict):
        """从字典加载（SaaS 模式：从数据库读取）"""
        return cls(
            api_account=config.get("api_account", ""),
            plain_password=config.get("plain_password", ""),
            private_key=config.get("private_key", ""),
        )

    def is_valid(self) -> bool:
        """检查是否所有必要字段都已配置"""
        return bool(self.api_account and self.plain_password and self.private_key)


def _md5(s: str) -> str:
    """MD5 哈希"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _compute_digest(auth: AuthConfig) -> str:
    """计算 body 中的 digest 值（业务参数签名）

    算法：Base64(MD5(apiAccount + 密文 + privateKey))

    其中密文 = MD5(明文密码 + jadada236t2).toUpperCase()
    """
    # Step 1: 计算密文
    password_md5 = _md5(auth.plain_password + SALT).upper()

    # Step 2: digest = Base64(MD5(apiAccount + 密文 + privateKey))
    raw = auth.api_account + password_md5 + auth.private_key
    digest_bytes = hashlib.md5(raw.encode("utf-8")).digest()
    return base64.b64encode(digest_bytes).decode("utf-8")


def _compute_biz_digest(auth: AuthConfig, customer_code: str) -> str:
    """计算 bizContent 内部的 digest（用于认证业务参数）"""
    password_md5 = _md5(auth.plain_password + SALT).upper()
    raw = customer_code + password_md5 + auth.private_key
    digest_bytes = hashlib.md5(raw.encode("utf-8")).digest()
    return base64.b64encode(digest_bytes).decode("utf-8")


def _build_headers(auth: AuthConfig, customer_code: str) -> dict:
    """构建请求 Header"""
    timestamp = int(time.time() * 1000)
    digest = _compute_digest(auth)
    return {
        "apiAccount": auth.api_account,
        "digest": digest,
        "timestamp": str(timestamp),
        "Content-Type": "application/json",
    }


def _build_request_body(customer_code: str, **biz_params) -> dict:
    """构建请求 Body，自动生成 bizContent 内部的 digest"""
    biz = {"customerCode": customer_code, **biz_params}
    return {"bizContent": json.dumps(biz, ensure_ascii=False)}


# ═══════════════════════════════════════════════════════════
# API 调用
# ═══════════════════════════════════════════════════════════

class JTApiError(Exception):
    """极兔 API 错误"""
    def __init__(self, code: str, message: str, raw: dict = None):
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{code}] {message}")


class JTApiClient:
    """极兔速递 API 客户端"""

    def __init__(self, auth: AuthConfig, customer_code: str,
                 base_url: str = API_BASE, timeout: int = 30):
        self.auth = auth
        self.customer_code = customer_code
        self.base_url = base_url
        self.timeout = timeout

    def _call(self, path: str, biz_params: dict) -> dict:
        """调用极兔 API"""
        url = f"{self.base_url}{path}"
        headers = _build_headers(self.auth, self.customer_code)
        body = {
            "apiAccount": self.auth.api_account,
            "digest": headers["digest"],
            "timestamp": headers["timestamp"],
            "bizContent": json.dumps(biz_params, ensure_ascii=False),
        }

        logger.info(f"[API] {path} → {url[:60]}...")

        resp = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=self.timeout,
        )

        if not resp.ok:
            logger.error(f"[API] HTTP {resp.status_code}: {resp.text[:300]}")
            raise JTApiError("HTTP_ERROR", f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        code = data.get("code", "")
        msg = data.get("msg", "")

        if code != "1":
            logger.warning(f"[API] 业务失败 [{code}]: {msg}")
            raise JTApiError(code, msg, raw=data)

        logger.info(f"[API] 成功: {msg}")
        return data.get("data", {})

    # ── 测试连接 ──

    def test_connection(self) -> dict:
        """测试极兔 API 连通性（轻量调用，验证凭证和签名）"""
        # 使用查询路由接口验证，请求一个不存在的运单号来测试连通性
        return self._call("/other/intercept", {
            "mailNo": "TEST_CONNECTION",
            "reason": "连接测试",
        })

    # ── 拦截下发 ──

    def intercept(self, mail_no: str, reason: str = "客户要求拦截退回",
                  apply_type_code: int = 4,
                  receive_info: dict = None) -> dict:
        """提交拦截请求

        Args:
            mail_no: 运单号
            reason: 拦截原因
            apply_type_code: 4=拦截退回
            receive_info: 收件信息（可选，用于回传参考）
        """
        biz = {
            "customerCode": self.customer_code,
            "digest": _compute_biz_digest(self.auth, self.customer_code),
            "mailNo": mail_no,
            "reason": reason,
            "applyTypeCode": apply_type_code,
        }
        if receive_info:
            biz.update(receive_info)

        return self._call("/other/intercept", biz)

    # ── 创建/修改订单（用于修改地址） ──

    def modify_address(self, txlogistic_id: str,
                       receiver_name: str, receiver_mobile: str,
                       receiver_province: str, receiver_city: str,
                       receiver_area: str, receiver_address: str,
                       sender_info: dict = None) -> dict:
        """修改订单收件地址

        原理：创建订单接口支持修改。如果 txlogisticId 存在且未揽件，
        直接修改已有订单。地址变更自动重新生成三段码，运单号不变。

        Args:
            txlogistic_id: 客户订单号
            receiver_name: 收件人姓名
            receiver_mobile: 收件人手机
            receiver_province: 收件省份
            receiver_city: 收件城市
            receiver_area: 收件区域
            receiver_address: 收件详细地址
            sender_info: 寄件信息（尽量提供，否则用默认值）
        """
        if sender_info is None:
            sender_info = {
                "name": "发件人",
                "mobile": "13800138000",
                "countryCode": "CHN",
                "prov": "广东省",
                "city": "深圳市",
                "area": "南山区",
                "address": "默认发件地址",
            }

        biz = {
            "customerCode": self.customer_code,
            "digest": _compute_biz_digest(self.auth, self.customer_code),
            "txlogisticId": txlogistic_id,
            "expressType": "EZ",
            "orderType": "2",
            "serviceType": "01",
            "deliveryType": "03",
            "payType": "PP_PM",
            "goodsType": "bm000006",
            "weight": "0.5",
            "totalQuantity": 1,
            "sender": sender_info,
            "receiver": {
                "name": receiver_name,
                "mobile": receiver_mobile,
                "countryCode": "CHN",
                "prov": receiver_province,
                "city": receiver_city,
                "area": receiver_area,
                "address": receiver_address,
            },
        }

        return self._call("/orderserve/create", biz)

    # ── 查询订单 ──

    def query_order(self, txlogistic_id: str = None,
                    mail_no: str = None) -> dict:
        """查询订单信息"""
        biz = {"customerCode": self.customer_code}
        if txlogistic_id:
            biz["txlogisticId"] = txlogistic_id
        if mail_no:
            biz["mailNo"] = mail_no
        return self._call("/orderserve/query", biz)


# ═══════════════════════════════════════════════════════════
# 错误码释义
# ═══════════════════════════════════════════════════════════

ERROR_CODES = {
    "145003031": "业务参数签名失败 — 请检查 API 凭证配置",
    "145002002": "运单重复,请勿使用相同运单号",
    "145003042": "修改订单失败",
    "145003060": "区域不合法",
    "145003061": "城市不合法",
    "145003062": "省份不合法",
    "145003064": "查不到数据",
    "145003041": "下单失败",
    "145003083": "发件人信息不全",
    "145003112": "该批次号运单无效",
    "145003101": "客户订单号已存在,无法下单",
    "145003201": "已取件状态不可修改 — 包裹已发出，无法拦截/改地址",
    "145003202": "已取消状态不可修改",
    "145003203": "更新订单失败，请稍后重试",
    "145003200": "服务类型不合法，请检查 serviceType 值",
    "145003340": "驿站编码只能英文与数字",
    "145003341": "驿站编码最长20字符",
}


def explain_error(code: str) -> str:
    """将极兔错误码转换为可读提示"""
    return ERROR_CODES.get(code, f"未知错误 [{code}]，请联系极兔技术支持")
