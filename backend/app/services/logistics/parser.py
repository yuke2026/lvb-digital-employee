"""驿递通 · 指令解析器

从飞书群消息中解析出操作指令。

支持指令格式（宽松匹配）：
  - 拦截退回 {运单号}
  - 修改地址 {运单号} [收件人:xxx] [电话:xxx] [地址:xxx]

运单号匹配：UT 开头的字母数字组合，或纯数字
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("驿递通.parser")


class OperationType(Enum):
    INTERCEPT = "intercept"       # 拦截退回
    MODIFY_ADDRESS = "modify_address"  # 修改地址
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    """解析后的指令"""
    operation: OperationType = OperationType.UNKNOWN
    mail_no: Optional[str] = None           # 运单号 (UT开头的)
    txlogistic_id: Optional[str] = None     # 客户订单号
    raw_text: str = ""
    confidence: float = 0.0

    # 修改地址的额外参数
    receiver_name: Optional[str] = None
    receiver_mobile: Optional[str] = None
    receiver_province: Optional[str] = None
    receiver_city: Optional[str] = None
    receiver_area: Optional[str] = None
    receiver_address: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.operation != OperationType.UNKNOWN and bool(self.mail_no or self.txlogistic_id)


# 运单号正则：UT 开头的字母数字组合，或纯数字
# 示例: UT0000456908252, UT0000456907255
MAIL_NO_PATTERN = re.compile(r"\b(UT\d{10,20})\b", re.IGNORECASE)
# 纯数字运单号（备用）
MAIL_NO_DIGITS = re.compile(r"\b(\d{12,20})\b")

# 键值对提取
KEY_VALUE_PATTERN = re.compile(r"(?:收件人|姓名|电话|手机|地址|省份|城市|区县)[：:]\s*([^\s,，、]+)")


def parse(text: str) -> ParsedCommand:
    """解析飞书群消息"""
    cmd = ParsedCommand(raw_text=text.strip())
    text_clean = text.strip()

    # 提取运单号（优先）
    mail_match = MAIL_NO_PATTERN.search(text_clean)
    if mail_match:
        cmd.mail_no = mail_match.group(1).upper()
    else:
        # 尝试纯数字
        digits_match = MAIL_NO_DIGITS.search(text_clean)
        if digits_match:
            cmd.mail_no = digits_match.group(1)

    # 检测操作类型 — 拦截退回
    if any(kw in text_clean for kw in ["拦截退回", "拦截", "退回"]):
        cmd.operation = OperationType.INTERCEPT
        cmd.confidence = 0.9
        logger.info(f"[解析] 拦截指令: mail_no={cmd.mail_no}")

    # 检测操作类型 — 修改地址
    elif any(kw in text_clean for kw in ["修改地址", "改地址", "改收件", "改寄件信息"]):
        cmd.operation = OperationType.MODIFY_ADDRESS

        # 提取 key-value 参数
        # 收件人/姓名
        name_m = re.search(r"(?:收件人|姓名)[：:]\s*(\S{2,10})", text_clean)
        if name_m:
            cmd.receiver_name = name_m.group(1)

        # 电话/手机
        phone_m = re.search(r"(?:电话|手机)[：:]\s*(1\d{10})", text_clean)
        if phone_m:
            cmd.receiver_mobile = phone_m.group(1)

        # 地址（比较复杂，可能是多个字段）
        addr_m = re.search(r"(?:地址|新地址)[：:]\s*(.+?)(?:\s*(?:收件人|电话|手机)[：:]|$)", text_clean)
        if addr_m:
            cmd.receiver_address = addr_m.group(1).strip()

        # 省份/城市/区县（可选，从地址里智能拆分）
        if cmd.receiver_address:
            prov_city = _parse_address(cmd.receiver_address)
            if prov_city:
                cmd.receiver_province, cmd.receiver_city, cmd.receiver_area = prov_city

        cmd.confidence = 0.85
        logger.info(f"[解析] 改地址指令: mail_no={cmd.mail_no}, "
                     f"收件人={cmd.receiver_name}, 手机={cmd.receiver_mobile}")

    # 未知指令
    else:
        cmd.confidence = 0.1
        logger.info(f"[解析] 未能识别指令: {text_clean[:50]}")

    return cmd


def _parse_address(full_address: str) -> Optional[tuple]:
    """从完整地址中拆分省/市/区

    示例: "广东省深圳市南山区科技南路18号" → ("广东省","深圳市","南山区")
    """
    # 省匹配
    prov_match = re.search(r"((?:北京|天津|上海|重庆)|(?:.{2,4}(?:省|自治区)))", full_address)
    if not prov_match:
        return None
    prov = prov_match.group(1)
    rest = full_address[prov_match.end():]

    # 市匹配
    city_match = re.search(r"(.+?(?:市|自治州|地区))", rest)
    if not city_match:
        return None
    city = city_match.group(1)
    rest = rest[city_match.end():]

    # 区/县匹配
    area_match = re.search(r"(.+?(?:区|县|县级市|镇))", rest)
    if not area_match:
        return None
    area = area_match.group(1)

    return prov, city, area


def format_intercept_response(mail_no: str, success: bool,
                              return_mail_no: str = None,
                              error_msg: str = None) -> str:
    """格式化拦截结果回复"""
    if success:
        msg = (
            f"✅ 拦截已提交\n"
            f"  运单号：{mail_no}\n"
            f"  状态：⏳ 等待极兔回执\n"
            f"  ────────\n"
            f"  ⚠️ 责任声明：您在群聊中发起此操作，"
            f"即代表收件人本人同意拦截退回。"
        )
    else:
        msg = (
            f"❌ 拦截失败\n"
            f"  运单号：{mail_no}\n"
            f"  原因：{error_msg or '未知错误'}\n"
            f"  ────────\n"
            f"  💡 建议联系极兔客服处理"
        )
    return msg


def format_modify_response(txlogistic_id: str, success: bool,
                           new_address: str = None,
                           sorting_code: str = None,
                           error_msg: str = None) -> str:
    """格式化地址修改结果回复"""
    if success:
        msg = (
            f"✅ 地址修改成功\n"
            f"  订单号：{txlogistic_id}\n"
            f"  新地址：{new_address or '已更新'}\n"
            f"  三段码：{sorting_code or '已重新生成'}\n"
            f"  ────────\n"
            f"  💡 运单号不变，三段码已根据新地址自动更新\n"
            f"  ⚠️ 责任声明：您发起此操作即代表收件人同意修改收件地址。"
        )
    else:
        msg = (
            f"❌ 地址修改失败\n"
            f"  订单号：{txlogistic_id}\n"
            f"  原因：{error_msg or '未知错误'}\n"
            f"  ────────\n"
            f"  💡 请在极兔后台手动操作，或联系极兔客服"
        )
    return msg


def format_callback_notification(mail_no: str, intercept_result: str,
                                 return_mail_no: str = None) -> str:
    """格式化拦截回传通知"""
    if intercept_result == "success":
        msg = (
            f"🔔 拦截结果通知\n"
            f"  运单号：{mail_no}\n"
            f"  结果：✅ 拦截成功\n"
        )
        if return_mail_no:
            msg += f"  退回单号：{return_mail_no}\n"
    else:
        msg = (
            f"🔔 拦截结果通知\n"
            f"  运单号：{mail_no}\n"
            f"  结果：❌ 拦截失败\n"
        )
    return msg
