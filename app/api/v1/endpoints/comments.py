"""评论回写 API (M08)。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import CommentLogResponse
from app.services.comment_service import CommentService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.post("/write/{task_id}")
async def write_approval_comment(
    task_id: int,
    db: Session = Depends(get_db),
):
    """接口: write_approval_comment(instance_id, review_id)

    将审查意见写回审批评论区。会自动获取 M07 生成的 comment_text。
    """
    service = CommentService(db)
    try:
        comment_log = await service.write_approval_comment(task_id)
        data = CommentLogResponse.model_validate(comment_log).model_dump(mode="json")
        status_msg = "回写成功" if comment_log.write_status == "success" else "回写失败"
        return success_response(data=data, message=status_msg)
    except ValueError as e:
        return error_response(str(e), code=400)
    except Exception as e:
        return error_response(f"评论回写失败: {e}")


@router.post("/retry/{task_id}")
async def retry_write_comment(
    task_id: int,
    db: Session = Depends(get_db),
):
    """重试评论回写（管理员手动触发）"""
    service = CommentService(db)
    try:
        comment_log = await service.retry_write(task_id)
        data = CommentLogResponse.model_validate(comment_log).model_dump(mode="json")
        return success_response(data=data, message="重试完成")
    except ValueError as e:
        return error_response(str(e), code=400)
    except Exception as e:
        return error_response(f"重试回写失败: {e}")


@router.get("/{task_id}")
def get_comment_log(
    task_id: int,
    db: Session = Depends(get_db),
):
    """查询任务最近的回写日志"""
    service = CommentService(db)
    log = service.get_comment_log(task_id)
    if not log:
        return error_response(f"任务 {task_id} 暂无回写日志", code=404)
    data = CommentLogResponse.model_validate(log).model_dump(mode="json")
    return success_response(data=data)
