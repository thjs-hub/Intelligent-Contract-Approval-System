"""规则命中记录 ORM 模型。

对应数据库表 rule_hits，每次 M06 规则审查命中一条规则即创建一条记录。
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, ForeignKey, String, Text, func

from app.models.base import Base


class RuleHit(Base):
    """规则命中记录表 ORM 模型"""

    __tablename__ = "rule_hits"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=False, index=True)
    # 关联规则 ID
    rule_id = Column(BigInteger, ForeignKey("review_rules.id"), nullable=False)
    # 命中证据原文片段
    evidence_text = Column(Text, nullable=True)
    # 命中位置标识
    evidence_position = Column(String(256), nullable=True)
    # 命中状态: hit / miss / error
    hit_status = Column(String(32), default="hit")
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<RuleHit(id={self.id}, task_id={self.task_id}, rule_id={self.rule_id})>"
