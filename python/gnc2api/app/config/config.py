"""
应用程序配置模块
"""

from typing import List
from pydantic_settings import BaseSettings

from app.core.constants import (
    API_VERSION,
    DEFAULT_FILTER_MODELS,
    DEFAULT_MODEL,
    DEFAULT_STREAM_CHUNK_SIZE,
    DEFAULT_STREAM_LONG_TEXT_THRESHOLD,
    DEFAULT_STREAM_MAX_DELAY,
    DEFAULT_STREAM_MIN_DELAY,
    DEFAULT_STREAM_SHORT_TEXT_THRESHOLD,
    DEFAULT_TIMEOUT,
    DEFAULT_X_GOOG_API_CLIENT,
)


class Settings(BaseSettings):
    """应用程序配置"""

    # API相关配置
    AUTH_TOKEN: str = ""
    API_PROVIDERS: List[str]
    ALLOWED_TOKENS: List[str]

    # 官方API密钥，用于获取模型列表
    OFFICIAL_API_KEY: str = ""

    # 模型相关配置
    TEST_MODEL: str = DEFAULT_MODEL
    SEARCH_MODELS: List[str] = ["gemini-2.0-flash-exp"]
    IMAGE_MODELS: List[str] = ["gemini-2.0-flash-exp"]
    FILTERED_MODELS: List[str] = DEFAULT_FILTER_MODELS

    SHOW_SEARCH_LINK: bool = True
    SHOW_THINKING_PROCESS: bool = True
    TOOLS_CODE_EXECUTION_ENABLED: bool = False

    MAX_FAILURES: int = 3
    MAX_TIMEOUT: int = DEFAULT_TIMEOUT
    X_GOOG_API_CLIENT: str = ""
    BASE_URL: str = f"https://generativelanguage.googleapis.com/{API_VERSION}"

    # 图像生成相关配置
    UPLOAD_PROVIDER: str = "smms"
    SMMS_SECRET_TOKEN: str = ""
    PICGO_API_KEY: str = ""
    CLOUDFLARE_IMGBED_URL: str = ""
    CLOUDFLARE_IMGBED_AUTH_CODE: str = ""

    # 流式输出优化器配置
    STREAM_OPTIMIZER_ENABLED: bool = False
    STREAM_MIN_DELAY: float = DEFAULT_STREAM_MIN_DELAY
    STREAM_MAX_DELAY: float = DEFAULT_STREAM_MAX_DELAY
    STREAM_SHORT_TEXT_THRESHOLD: int = DEFAULT_STREAM_SHORT_TEXT_THRESHOLD
    STREAM_LONG_TEXT_THRESHOLD: int = DEFAULT_STREAM_LONG_TEXT_THRESHOLD
    STREAM_CHUNK_SIZE: int = DEFAULT_STREAM_CHUNK_SIZE

    def __init__(self):
        super().__init__()
        if not self.AUTH_TOKEN:
            self.AUTH_TOKEN = self.ALLOWED_TOKENS[0] if self.ALLOWED_TOKENS else ""

        if not self.X_GOOG_API_CLIENT:
            self.X_GOOG_API_CLIENT = DEFAULT_X_GOOG_API_CLIENT

    class Config:
        env_file = ".env"


# 创建全局配置实例
settings = Settings()
