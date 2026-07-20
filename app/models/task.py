"""审批任务 ORM 模型。

对应数据库表 approval_tasks，是整个审查流程的数据入口。
每条记录代表一个从外部审批系统同步过来的待处理审批单。

关键字段:
  - approval_code: 审批编号，唯一业务标识，用于 M03 去重判断
  - task_status: 任务状态机 (pending -> parsing -> reviewing -> blocked/done)
  - write_status: 评论回写状态机 (not_written -> writing -> success/failed)
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, Enum, String, func

from app.models.base import Base


class ApprovalTask(Base):
    """审批任务表 ORM 模型"""

    __tablename__ = "approval_tasks"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 审批编号 — 唯一业务标识，去重判断的核心字段
    approval_code = Column(String(128), unique=True, nullable=False, index=True)
    # 审批标题
    approval_title = Column(String(512), nullable=True)
    # 申请人姓名
    applicant_name = Column(String(128), nullable=True)
    # 任务状态机: pending -> parsing -> reviewing -> blocked/done
    task_status = Column(
        Enum("pending", "parsing", "reviewing", "blocked", "done", name="task_status_enum"),
        default="pending",
        nullable=False,
    )
    # 评论回写状态机: not_written -> writing -> success/failed
    write_status = Column(
        Enum("not_written", "writing", "success", "failed", name="write_status_enum"),
        default="not_written",
        nullable=False,
    )
    # 阻塞原因 — 仅在 task_status=blocked 时有值
    block_reason = Column(String(1024), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ApprovalTask(id={self.id}, code={self.approval_code}, status={self.task_status})>"
