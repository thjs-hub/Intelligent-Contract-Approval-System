"""合同附件管理服务 (M02)。

负责从审批系统下载附件到本地文件系统，并记录元数据到 approval_attachments 表。
下载失败时触发 M10 异常阻塞。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attachment import ApprovalAttachment
from app.services.adapters.base import get_approval_adapter
from app.services.block_handler import BlockHandler
from app.services.file_storage import FileStorageService
from app.services.task_log_service import log_error, log_info


class AttachmentService:
    """合同附件管理服务"""

    def __init__(self, db: Session):
        self.db = db
        self.storage = FileStorageService()

    async def download_attachment(
        self,
        task_id: int,
        attachment_id: str,
        file_name: str,
    ) -> ApprovalAttachment:
        """下载单个附件并保存

        接口: download_contract_attachment(instance_id, attachment_id, file_name)

        流程:
          1. 创建 attachment 记录 (download_status=downloading)
          2. 调用审批系统适配器下载文件二进制
          3. 保存到本地文件系统 + 计算 MD5
          4. 更新记录 status=success
          5. 失败时触发 M10 阻塞

        参数:
          task_id: 任务 ID
          attachment_id: 外部附件 ID
          file_name: 文件名

        返回:
          ApprovalAttachment 对象（含 file_path / file_md5 等字段）
        """
        # 1. 创建附件记录
        attachment = ApprovalAttachment(
            task_id=task_id,
            file_name=file_name,
            file_type=FileStorageService.detect_file_type(file_name),
            external_attachment_id=attachment_id,
            download_status="downloading",
        )
        self.db.add(attachment)
        self.db.flush()
        log_info(self.db, task_id, "M02", f"开始下载附件: {file_name}")

        # 2. 调用审批系统下载文件
        try:
            adapter = get_approval_adapter()
            content = await adapter.download_attachment(attachment_id)
        except Exception as e:
            attachment.download_status = "failed"
            attachment.download_error = str(e)[:1000]
            self.db.commit()
            # ===== M10 异常阻塞 =====
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"附件下载失败: {e}", module="M02"
            )
            log_error(self.db, task_id, "M02", f"附件下载失败: {e}")
            return attachment

        # 3. 保存文件 + 校验
        try:
            file_path = await self.storage.save_file(task_id, file_name, content)
        except Exception as e:
            attachment.download_status = "failed"
            attachment.download_error = f"文件保存失败: {e}"
            self.db.commit()
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"文件保存失败: {e}", module="M02"
            )
            log_error(self.db, task_id, "M02", f"文件保存失败: {e}")
            return attachment

        attachment.file_path = file_path
        attachment.file_size = len(content)
        attachment.file_md5 = FileStorageService.compute_md5(content)
        attachment.download_status = "success"

        self.db.commit()
        log_info(
            self.db,
            task_id,
            "M02",
            f"附件下载完成: {file_name}, 大小={len(content)}字节, MD5={attachment.file_md5}",
        )
        return attachment

    async def download_all_for_task(self, task_id: int) -> list[ApprovalAttachment]:
        """下载某审批单的全部附件

        流程:
          1. 通过 M01 适配器获取审批详情中的附件列表
          2. 遍历并下载每个附件

        参数:
          task_id: 任务 ID

        返回:
          已下载的 ApprovalAttachment 列表
        """
        # 从 ApprovalTask 获取 approval_code 用于调用适配器
        from app.models.task import ApprovalTask

        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task is None:
            log_error(self.db, task_id, "M02", f"任务不存在: {task_id}")
            return []

        try:
            adapter = get_approval_adapter()
            detail = await adapter.fetch_approval_detail(task.approval_code)
        except Exception as e:
            log_error(self.db, task_id, "M02", f"获取审批详情失败: {e}")
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"获取审批详情失败: {e}", module="M02"
            )
            return []

        attachments_list = detail.get("attachments", [])
        results: list[ApprovalAttachment] = []
        for att_info in attachments_list:
            attachment = await self.download_attachment(
                task_id=task_id,
                attachment_id=att_info["attachment_id"],
                file_name=att_info["file_name"],
            )
            results.append(attachment)

        return results

    def list_attachments(self, task_id: int) -> list[ApprovalAttachment]:
        """查询任务的所有附件"""
        stmt = (
            select(ApprovalAttachment)
            .where(ApprovalAttachment.task_id == task_id)
            .order_by(ApprovalAttachment.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    def get_attachment(self, attachment_id: int) -> Optional[ApprovalAttachment]:
        """按 ID 查询单个附件"""
        return self.db.scalar(
            select(ApprovalAttachment).where(ApprovalAttachment.id == attachment_id)
        )
