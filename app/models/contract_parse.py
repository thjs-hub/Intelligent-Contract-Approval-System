"""合同解析结果 ORM 模型。

对应数据库表 contract_parses，存储 M04 文档解析模块的结构化输出。
basic_info_json 和 clause_info_json 为 JSON 字段，存储带原文证据的字段提取结果。
"""

from sqlalchemy import Integer, JSON, BigInteger, Column, DateTime, ForeignKey, String, Text, func

from app.models.base import Base


class ContractParse(Base):
    """合同解析结果表 ORM 模型"""

    __tablename__ = "contract_parses"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID（一对一）
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=False, unique=True)
    # 基本信息 JSON — 包含 contract_title/contract_number/party_a/party_b/contract_amount 等
    basic_info_json = Column(JSON, nullable=True)
    # 条款信息 JSON — 包含 payment_clause/delivery_clause 等 8 类条款
    clause_info_json = Column(JSON, nullable=True)
    # 解析状态: pending / parsing / success / failed / pending_ocr
    parse_status = Column(String(32), default="pending")
    # 解析失败原因
    parse_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ContractParse(id={self.id}, task_id={self.task_id}, status={self.parse_status})>"
