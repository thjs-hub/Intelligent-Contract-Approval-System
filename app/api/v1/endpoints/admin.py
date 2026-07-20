"""系统管理 API (M10)。

提供管理员视角的功能:
  - GET  /admin/tasks/blocked     获取所有阻塞任务
  - POST /admin/tasks/{id}/retry  重试阻塞任务
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.task import ApprovalTaskResponse
from app.services.block_handler import BlockHandler
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/tasks/blocked")
def list_blocked_tasks(db: Session = Depends(get_db)):
    """获取所有阻塞任务列表"""
    tasks = BlockHandler.get_blocked_tasks(db)
    data = [
        ApprovalTaskResponse.model_validate(t).model_dump(mode="json") for t in tasks
    ]
    return success_response(data=data, message=f"共 {len(data)} 条阻塞任务")


@router.post("/tasks/{task_id}/retry")
async def retry_blocked_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """重试阻塞任务

    根据原阻塞环节自动决定重试起点:
      - 附件/解析/OCR 错误 → 重新进入 parsing 阶段
      - 审查/回写错误 → 重新进入 reviewing 阶段
    """
    try:
        retry_from = BlockHandler.retry_task(db, task_id)
        return success_response(
            data={"retry_from": retry_from, "task_id": task_id},
            message=f"任务 {task_id} 已从 {retry_from} 阶段恢复",
        )
    except ValueError as e:
        return error_response(str(e), code=400)


@router.get("/config")
def get_system_config():
    """获取当前系统配置（脱敏，供管理页"接入配置" Tab 展示）"""
    data = {
        "approval_adapter": settings.APPROVAL_ADAPTER,
        "ocr_engine": settings.OCR_ENGINE,
        "extractor_type": settings.EXTRACTOR_TYPE,
        "comment_max_retry": settings.COMMENT_MAX_RETRY,
        # TODO: 第三阶段接入配置表单后补充更多配置项
    }
    return success_response(data=data, message="当前系统配置")
