"""唯一性去重服务 (M03)。

按 approval_code（审批编号）作为唯一业务标识，确保同一审批单不会重复创建任务。
去重逻辑作为 M01 的嵌入式服务，不暴露独立 API，但封装为独立类便于测试和复用。
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import ApprovalTask


class DedupService:
    """唯一性去重服务

    提供幂等的审批单创建/更新能力:
      - 首次出现的 approval_code → 创建新任务，返回 (task, is_new=True)
      - 已存在的 approval_code → 仅更新元信息，返回 (task, is_new=False)
    """

    @staticmethod
    def check_and_resolve(
        db: Session,
        approval_code: str,
        **update_fields: Any,
    ) -> tuple[ApprovalTask, bool]:
        """检查去重并返回 (task, is_new)

        参数:
          db: 数据库会话
          approval_code: 审批编号（唯一业务标识）
          update_fields: 需要更新的字段，如 approval_title / applicant_name

        返回:
          (task, is_new) — task 为本地任务对象，is_new 表示是否本次新建

        说明:
          - 已存在记录时，update_fields 中非 None 的字段会被更新
          - 不在此处 commit，由调用方事务统一提交
        """
        existing = db.scalar(
            select(ApprovalTask).where(ApprovalTask.approval_code == approval_code)
        )

        if existing is not None:
            # 去重命中：仅更新非 None 字段，保留原值不被 None 覆盖
            if update_fields:
                for key, value in update_fields.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
            return existing, False

        # 首次出现：创建新任务
        # 仅传递 ApprovalTask 实际拥有的字段，避免传入非法字段引发错误
        valid_fields = {
            k: v
            for k, v in update_fields.items()
            if hasattr(ApprovalTask, k) and v is not None
        }
        new_task = ApprovalTask(
            approval_code=approval_code,
            task_status="pending",
            write_status="not_written",
            **valid_fields,
        )
        db.add(new_task)
        db.flush()  # 立即获取 new_task.id
        return new_task, True
