"""评论回写服务 (M08)。

主入口: write_approval_comment(task_id)
职责:
  1. 获取 M07 生成的审查意见 (comment_text)
  2. 调用审批系统适配器写入评论区
  3. 记录回写状态: not_written → writing → success/failed
  4. 失败时记录原因，支持手动重试（重试次数上限 COMMENT_MAX_RETRY）
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.comment_log import CommentLog
from app.models.review_result import ReviewResult
from app.models.task import ApprovalTask
from app.services.adapters.base import get_approval_adapter
from app.services.task_log_service import log_error, log_info


class CommentService:
    """评论回写服务"""

    # 最大重试次数（从配置读取，默认 3）
    MAX_RETRY: int = getattr(settings, "COMMENT_MAX_RETRY", 3)

    def __init__(self, db: Session):
        self.db = db

    async def write_approval_comment(self, task_id: int) -> CommentLog:
        """接口: write_approval_comment(instance_id, review_id)

        将审查意见写回审批评论区。

        参数:
          task_id: 任务 ID

        返回:
          CommentLog 对象（含回写状态和响应文本）

        异常:
          ValueError: 任务无审查结果或审查意见为空
        """
        # 1. 获取审查结果
        result = self.db.scalar(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )

        if not result:
            raise ValueError(f"任务 {task_id} 尚无审查结果，请先执行审查")

        if not result.comment_text:
            raise ValueError(f"任务 {task_id} 审查意见为空")

        # 2. 获取审批任务
        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 3. 获取已有的最近一条回写日志（用于累计重试次数）
        last_log = self.db.scalar(
            select(CommentLog)
            .where(CommentLog.task_id == task_id)
            .order_by(CommentLog.id.desc())
        )

        # 创建新的回写日志
        retry_count = (last_log.retry_count if last_log else 0) + 1
        comment_log = CommentLog(
            task_id=task_id,
            write_status="writing",
            retry_count=retry_count,
        )
        self.db.add(comment_log)

        task.write_status = "writing"
        self.db.flush()
        log_info(
            self.db,
            task_id,
            "M08",
            f"开始回写评论 (第 {retry_count} 次尝试)",
        )

        # 4. 调用审批系统回写 API
        try:
            adapter = get_approval_adapter()
            response = await adapter.write_comment(
                instance_id=task.approval_code,
                comment_text=result.comment_text,
            )

            # 成功
            comment_log.write_status = "success"
            comment_log.write_response_text = str(response)[:2000]
            task.write_status = "success"
            log_info(self.db, task_id, "M08", "评论回写成功")

        except Exception as e:
            # 失败
            comment_log.write_status = "failed"
            comment_log.write_response_text = str(e)[:2000]
            task.write_status = "failed"
            log_error(self.db, task_id, "M08", f"评论回写失败: {e}")

            # 判断是否还可自动重试
            if retry_count < self.MAX_RETRY:
                log_info(
                    self.db,
                    task_id,
                    "M08",
                    f"可重试 (已尝试 {retry_count}/{self.MAX_RETRY})，"
                    f"请管理员从管理界面手动触发重试",
                )
                # TODO: 第三阶段可加入异步重试队列自动重试

        self.db.commit()
        return comment_log

    async def retry_write(self, task_id: int) -> CommentLog:
        """重试回写（管理员手动触发）

        参数:
          task_id: 任务 ID

        返回:
          新的 CommentLog 对象
        """
        return await self.write_approval_comment(task_id)

    def get_comment_log(self, task_id: int) -> CommentLog | None:
        """查询任务最近的回写日志"""
        return self.db.scalar(
            select(CommentLog)
            .where(CommentLog.task_id == task_id)
            .order_by(CommentLog.id.desc())
        )
