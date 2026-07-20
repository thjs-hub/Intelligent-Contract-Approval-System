"""审批待办接入服务 (M01)。

主流程:
  1. 通过适配器从外部审批系统拉取待处理审批单
  2. 调用 M03 DedupService 按 approval_code 去重
  3. 新任务创建 / 已有任务更新元信息
  4. 通过 M09 记录日志
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import ApprovalTask
from app.services.adapters.base import get_approval_adapter
from app.services.dedup_service import DedupService
from app.services.task_log_service import log_error, log_info


class ApprovalService:
    """审批待办接入服务"""

    def __init__(self, db: Session):
        self.db = db
        self.adapter = get_approval_adapter()

    async def list_pending_approvals(self, limit: int = 20) -> list[ApprovalTask]:
        """主流程 Step 1: 拉取待处理审批单列表

        流程:
          1. 调用适配器获取外部数据
          2. 调用 M03 去重 (创建新任务 / 更新已有任务)
          3. 记录 M09 日志

        参数:
          limit: 拉取条数上限

        返回:
          本地 ApprovalTask 对象列表
        """
        try:
            raw_items = await self.adapter.fetch_pending_approvals(limit)
        except Exception as e:
            log_error(self.db, None, "M01", f"拉取审批单失败: {e}")
            raise

        tasks: list[ApprovalTask] = []
        for item in raw_items:
            approval_code = item["approval_code"]

            # ===== 调用 M03 去重逻辑 =====
            task, is_new = DedupService.check_and_resolve(
                self.db,
                approval_code,
                approval_title=item.get("approval_title"),
                applicant_name=item.get("applicant_name"),
            )

            tasks.append(task)

            # ===== M09 日志记录 =====
            if is_new:
                log_info(self.db, task.id, "M01", f"新建审批任务: {approval_code}")
            else:
                log_info(self.db, task.id, "M01", f"更新已有审批任务: {approval_code}")

        self.db.commit()
        return tasks

    def get_approval_detail(self, approval_code: str) -> Optional[ApprovalTask]:
        """查询本地已存储的审批任务详情

        参数:
          approval_code: 审批编号

        返回:
          ApprovalTask 对象，不存在时返回 None
        """
        return self.db.scalar(
            select(ApprovalTask).where(ApprovalTask.approval_code == approval_code)
        )

    def get_task_by_id(self, task_id: int) -> Optional[ApprovalTask]:
        """按主键 ID 查询任务"""
        return self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))

    def list_local_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[ApprovalTask]:
        """查询本地已存储的任务列表

        参数:
          status: 可选状态过滤 (pending/parsing/reviewing/blocked/done)
          limit: 返回条数上限
        """
        stmt = select(ApprovalTask).order_by(ApprovalTask.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(ApprovalTask.task_status == status)
        return list(self.db.scalars(stmt))
