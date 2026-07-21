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

    # ===== 第三阶段新增配置项 — AI 审查能力 =====
    # 所有 AI 能力默认关闭，可通过 .env 渐进式开启。
    # 关闭时自动回退到第二阶段基础行为，不破坏端到端闭环。

    # --- LLM 智能审查 (P3-4) ---
    # 是否启用 LLM 智能审查（需要配置 LLM_ENDPOINT 和 LLM_API_KEY）
    LLM_ENABLED: bool = False
    # LLM API 端点地址（OpenAI 兼容格式）
    LLM_ENDPOINT: str = ""
    # LLM API 密钥（请通过环境变量注入，不要硬编码）
    LLM_API_KEY: str = ""
    # 默认 LLM 模型名（如 qwen-plus / deepseek-chat / gpt-4o-mini）
    LLM_MODEL: str = "qwen-plus"
    # LLM 请求超时（秒）
    LLM_TIMEOUT: int = 60
    # LLM 单次响应最大 token 数
    LLM_MAX_TOKENS: int = 4096
    # LLM 采样温度（审查场景需要稳定输出，建议低温度）
    LLM_TEMPERATURE: float = 0.1

    # --- 语义匹配 (P3-2) ---
    # 是否启用语义匹配模式（需要安装 sentence-transformers）
    SEMANTIC_ENABLED: bool = False
    # 语义匹配相似度阈值（≥此值视为命中，0~1，越高越严格）
    SEMANTIC_THRESHOLD: float = 0.75
    # 向量编码模型名（HuggingFace 模型标识符）
    SEMANTIC_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # --- OCR 布局分析 (P3-3) ---
    # 是否启用 OCR 布局分析（识别标题/段落/表格区域）
    OCR_USE_LAYOUT: bool = False
    # 是否启用 OCR 表格识别
    OCR_TABLE_RECOGNITION: bool = False

    # --- NLP 信息抽取 (P3-1) ---
    # 是否启用 NLP 信息抽取增强（NER 模型）
    NLP_EXTRACTOR_ENABLED: bool = False
    # NLP 模型名（用于 NER，HanLP/spaCy/HuggingFace 模型标识符）
    NLP_MODEL: str = "hfl/chinese-roberta-wwm-ext"

    # --- AI 编排与报告 ---
    # AI 审查编排总开关（关闭时仅走第二阶段规则审查流程）
    AI_REVIEW_ENABLED: bool = False
    # 是否启用报告 AI 增强（AI 摘要 + 风险分布）
    AI_REPORT_ENHANCE: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
