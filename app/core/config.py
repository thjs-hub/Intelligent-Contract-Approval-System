"""应用配置 —— 通过 Pydantic Settings 从 .env 读取。

第二阶段新增配置项：
  - APPROVAL_ADAPTER: 审批系统适配器类型，默认 "mock"（第三阶段可切换为 dingtalk/feishu/wecom）
  - OCR_ENGINE: OCR 引擎类型，默认 "paddle"（可选 "tesseract"）
  - EXTRACTOR_TYPE: 文档解析提取器类型，默认 "regex"（第三阶段可切换为 "nlp"）
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "ContractReviewSystem"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # 服务
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # API
    API_V1_PREFIX: str = "/api/v1"

    # 数据库
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "contract_review"
    DB_POOL_SIZE: int = 10
    DB_POOL_RECYCLE: int = 3600

    @property
    def DATABASE_URL(self) -> str:
        """组装 MySQL 数据库连接字符串"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """将逗号分隔的 CORS 域名拆分为列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ===== 第二阶段新增配置项 =====

    # 审批系统适配器: mock / dingtalk / feishu / wecom
    # 第二阶段仅实现 mock，其余为第三阶段扩展点
    APPROVAL_ADAPTER: str = "mock"

    # OCR 引擎类型: paddle / tesseract
    OCR_ENGINE: str = "paddle"

    # 文档解析提取器: regex / nlp
    # 第二阶段仅实现 regex，nlp 为第三阶段扩展点
    EXTRACTOR_TYPE: str = "regex"

    # 评论回写最大重试次数
    COMMENT_MAX_RETRY: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
