"""AI 审查结果 ORM 模型 — 第三阶段新增。

对应数据库表 ai_review_results，存储 P3-4 LLM 智能审查器输出的
结构化风险项、总体评估、缺失条款及 AI 生成的审查摘要。

每条审批任务对应唯一一条 AI 审查结果（一对一），
由 AIOrchestrator 在编排流程中创建或更新。
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import JSON

from app.models.base import Base


class AIReviewResult(Base):
    """AI 审查结果表 ORM 模型

    字段说明:
      - risk_items_json: LLM 识别的风险项列表，每项包含
          {risk_type, risk_level, description, evidence, suggestion}
      - overall_assessment: LLM 对合同整体风险的自然语言评估
      - missing_clauses_json: LLM 识别的缺失关键条款列表
      - ai_summary: LLM 综合规则结果与 AI 风险项生成的审查摘要
      - model_name: 实际使用的 LLM 模型名（便于成本追踪）
      - token_usage: 本次 LLM 调用消耗的 token 数
    """

    __tablename__ = "ai_review_results"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    # 关联审批任务 ID（一对一）
    task_id = Column(
        BigInteger,
        ForeignKey("approval_tasks.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    # LLM 识别的风险项列表（JSON 数组）
    risk_items_json = Column(JSON, nullable=True)
    # LLM 总体评估文本
    overall_assessment = Column(Text, nullable=True)
    # 缺失的关键条款列表（JSON 数组）
    missing_clauses_json = Column(JSON, nullable=True)
    # AI 生成的审查摘要
    ai_summary = Column(Text, nullable=True)
    # 使用的 LLM 模型名
    model_name = Column(String(128), nullable=True)
    # token 消耗量
    token_usage = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<AIReviewResult(id={self.id}, task_id={self.task_id}, "
            f"model={self.model_name})>"
        )
