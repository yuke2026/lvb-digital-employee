"""插件配置模型 — 存储每家企业每个插件的配置（如物流客服的极兔API凭证）"""
import json
from datetime import datetime
from sqlalchemy import String, Text, DateTime, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PluginConfig(Base):
    __tablename__ = "plugin_configs"

    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plugin: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        PrimaryKeyConstraint("org_id", "plugin"),
    )

    def get_config_dict(self) -> dict:
        """解析 config JSON -> dict"""
        if not self.config:
            return {}
        if isinstance(self.config, dict):
            return self.config
        try:
            return json.loads(self.config)
        except (json.JSONDecodeError, TypeError):
            return {}
