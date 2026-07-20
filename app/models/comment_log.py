"""评论回写日志 ORM 模型。

对应数据库表 comment_logs，记录 M08 评论回写操作的全生命周期。
支持失败重试，每次重试创建一条新记录。
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, Enum, ForeignKey, String, Text, func

from app.models.base import Base


class CommentLog(Base):
    """评论回写日志表 ORM 模型"""

    __tablename__ = "comment_logs"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=False, index=True)
    # 回写状态: not_written / writing / success / failed
    write_status = Column(
        Enum("not_written", "writing", "success", "failed", name="comment_status_enum"),
        default="not_written",
        nullable=False,
    )
    # 审批系统返回的响应文本（成功或失败原因）
    write_response_text = Column(Text, nullable=True)
    # 重试次数
    retry_count = Column(BigInteger, default=0)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<CommentLog(id={self.id}, task_id={self.task_id}, "
            f"status={self.write_status}, retry={self.retry_count})>"
        )
