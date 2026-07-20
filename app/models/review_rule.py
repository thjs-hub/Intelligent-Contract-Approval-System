"""审查规则 ORM 模型。

对应数据库表 review_rules，存储预设的审查规则。
match_mode 决定匹配策略: keyword (关键词) / regex (正则) / semantic (语义，第三阶段)。
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, Enum, String, Text, func

from app.models.base import Base


class ReviewRule(Base):
    """审查规则表 ORM 模型"""

    __tablename__ = "review_rules"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 规则编码 — 唯一标识，如 R001 / R002
    rule_code = Column(String(64), unique=True, nullable=False, index=True)
    # 规则名称
    rule_name = Column(String(256), nullable=False)
    # 风险等级: 低 / 中 / 高
    risk_level = Column(Enum("低", "中", "高", name="risk_level_enum"), nullable=False)
    # 规则状态: enabled / disabled
    rule_status = Column(
        Enum("enabled", "disabled", name="rule_status_enum"),
        default="enabled",
        nullable=False,
    )
    # 匹配模式: keyword / regex / semantic
    match_mode = Column(
        Enum("keyword", "regex", "semantic", name="match_mode_enum"),
        nullable=False,
    )
    # 匹配文本 — keyword 模式为逗号分隔关键词；regex 模式为正则表达式
    match_text = Column(Text, nullable=False)
    # 处置建议文本
    suggestion_text = Column(Text, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReviewRule(id={self.id}, code={self.rule_code}, name={self.rule_name})>"
