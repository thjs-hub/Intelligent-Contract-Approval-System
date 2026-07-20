"""任务运行日志 ORM 模型。

对应数据库表 task_logs，由 M09 日志服务写入，记录每个任务在每个模块的关键操作日志。
日志按 task_id 关联，便于全链路追踪。
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, Enum, ForeignKey, String, Text, func

from app.models.base import Base


class TaskLog(Base):
    """任务运行日志表 ORM 模型"""

    __tablename__ = "task_logs"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID（允许为空，用于系统级日志）
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=True, index=True)
    # 日志级别: INFO / WARN / ERROR
    log_level = Column(
        Enum("INFO", "WARN", "ERROR", name="log_level_enum"),
        default="INFO",
        nullable=False,
    )
    # 日志类型 — 模块标识: M01 / M02 / M04 / M05 / M06 / M07 / M08 / M09 / M10
    log_type = Column(String(64), nullable=True)
    # 日志内容
    log_content = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<TaskLog(id={self.id}, task_id={self.task_id}, "
            f"level={self.log_level}, type={self.log_type})>"
        )
