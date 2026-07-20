"""审查结果 ORM 模型。

对应数据库表 review_results，存储 M07 输出的最终审查结论。
每条审批任务对应唯一一条审查结果（一对一）。
"""

from sqlalchemy import Integer, JSON, BigInteger, Column, DateTime, Enum, ForeignKey, String, Text, func

from app.models.base import Base


class ReviewResult(Base):
    """审查结果表 ORM 模型"""

    __tablename__ = "review_results"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID（一对一）
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=False, unique=True)
    # 总体风险等级: 低 / 中 / 高
    overall_risk_level = Column(
        Enum("低", "中", "高", name="result_risk_enum"),
        nullable=False,
    )
    # 审查摘要文本
    summary_text = Column(Text, nullable=True)
    # 审批关注点列表 JSON，如 ["关注点1", "关注点2"]
    focus_points_json = Column(JSON, nullable=True)
    # 回写评论文本（M08 即将写入审批系统的内容）
    comment_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ReviewResult(id={self.id}, task_id={self.task_id}, "
            f"risk={self.overall_risk_level})>"
        )
