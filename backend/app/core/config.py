"""应用配置"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "百应智星数字员工"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lvb_employee"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/lvb_employee"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Feishu (Lark)
    LARK_APP_ID: str = ""
    LARK_APP_SECRET: str = ""
    LARK_VERIFICATION_TOKEN: str = ""
    LARK_ENCRYPT_KEY: str = ""

    # S3 / MinIO
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "lvb-employee"

    # SMTP / Email
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "百应智星数字员工"

    # Push notifications
    PUSH_ENABLED: bool = False
    PUSH_PROVIDER: str = "fcmp"  # fcmp, jiguang, getui

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
