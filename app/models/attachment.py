"""合同附件 ORM 模型。

对应数据库表 approval_attachments，记录每个审批任务下下载的附件元数据。
file_type 决定路由到 M04（文档解析）还是 M05（OCR）。
"""

from sqlalchemy import Integer, BigInteger, Column, DateTime, ForeignKey, String, func

from app.models.base import Base


class ApprovalAttachment(Base):
    """审批附件表 ORM 模型"""

    __tablename__ = "approval_attachments"

    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    # 关联审批任务 ID
    task_id = Column(BigInteger, ForeignKey("approval_tasks.id"), nullable=False, index=True)
    # 文件名
    file_name = Column(String(512), nullable=True)
    # 文件类型: docx / pdf / image / unknown
    file_type = Column(String(64), nullable=True)
    # 本地存储绝对路径
    file_path = Column(String(1024), nullable=True)
    # 文件大小（字节）
    file_size = Column(BigInteger, default=0)
    # 文件 MD5 校验值，用于完整性校验
    file_md5 = Column(String(64), default="")
    # 下载状态: pending / downloading / success / failed
    download_status = Column(String(32), default="pending")
    # 下载失败原因
    download_error = Column(String(1024), nullable=True)
    # 外部附件 ID（来自审批系统）
    external_attachment_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ApprovalAttachment(id={self.id}, task_id={self.task_id}, name={self.file_name})>"
