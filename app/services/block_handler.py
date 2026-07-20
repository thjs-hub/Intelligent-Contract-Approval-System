"""异常阻塞处理服务 (M10)。

当任何环节出现异常（附件缺失、解析失败、OCR 无法识别、回写失败等）时，
自动将任务标记为 blocked 状态，记录阻塞原因，并提供人工重试入口。

重试策略:
  - 附件/解析/OCR 类错误 → 重新进入 parsing 阶段
  - 审查/回写类错误 → 重新进入 reviewing 阶段
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import ApprovalTask
from app.services.task_log_service import get_task_logs, log_error, log_info

# 阻塞原因 → 重试阶段映射
# 附件/解析/OCR 错误从 parsing 阶段重试；其余从 reviewing 阶段重试
_BLOCK_MODULE_TO_RETRY_STAGE = {
    "M02": "parsing",
    "M04": "parsing",
    "M05": "parsing",
}


class BlockHandler:
    """异常阻塞处理服务"""

    # 各模块异常触发条件说明（仅供文档参考）
    BLOCK_REASONS = {
        "M01": "审批单拉取失败",
        "M02": "附件下载失败",
        "M04": "文档解析失败",
        "M05": "OCR识别失败",
        "M06": "规则审查异常",
        "M08": "评论回写失败",
    }

    @staticmethod
    def trigger_block(
        db: Session,
        task_id: int,
        reason: str,
        module: str = "M10",
    ) -> None:
        """触发任务阻塞

        参数:
          db: 数据库会话
          task_id: 任务 ID
          reason: 阻塞原因（人类可读）
          module: 触发阻塞的模块标识 (M01/M02/M04/M05/M06/M08)，
                  用于重试时判断恢复起点。默认 "M10" 表示由阻塞处理模块自身触发。
        """
        task = db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task is None:
            log_error(db, task_id, "M10", f"触发阻塞失败: 任务不存在, reason={reason}")
            return

        old_status = task.task_status
        task.task_status = "blocked"
        task.block_reason = reason[:1000] if reason else None
        db.flush()
        log_error(
            db,
            task_id,
            module,
            f"任务阻塞: {reason} (原状态: {old_status})",
        )

    @staticmethod
    def retry_task(db: Session, task_id: int) -> str:
        """重试阻塞任务，根据原阻塞环节决定重试起点

        参数:
          db: 数据库会话
          task_id: 任务 ID

        返回:
          重试起始阶段: "parsing" 或 "reviewing"

        异常:
          ValueError: 任务不存在或不处于 blocked 状态
        """
        task = db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))

        if task is None:
            raise ValueError(f"任务不存在: {task_id}")

        if task.task_status != "blocked":
            raise ValueError(f"任务 {task_id} 不处于阻塞状态，无法重试")

        # 从最后一条错误日志推断阻塞环节
        logs = get_task_logs(db, task_id, limit=10)
        last_error = next((log for log in logs if log.log_level == "ERROR"), None)

        if last_error and last_error.log_type in _BLOCK_MODULE_TO_RETRY_STAGE:
            # 附件/解析/OCR 问题 → 重新进入解析阶段
            retry_from = _BLOCK_MODULE_TO_RETRY_STAGE[last_error.log_type]
            task.task_status = "parsing"
        else:
            # 审查/回写问题 → 重新进入审查阶段
            retry_from = "reviewing"
            task.task_status = "reviewing"

        # 清除阻塞原因
        task.block_reason = None
        db.commit()
        log_info(db, task_id, "M10", f"任务重试: 从 {retry_from} 阶段恢复")
        return retry_from

    @staticmethod
    def get_blocked_tasks(db: Session) -> list[ApprovalTask]:
        """获取所有阻塞任务（供管理员界面使用）

        返回:
          按更新时间倒序排列的 blocked 任务列表
        """
        stmt = (
            select(ApprovalTask)
            .where(ApprovalTask.task_status == "blocked")
            .order_by(ApprovalTask.updated_at.desc())
        )
        return list(db.scalars(stmt))
