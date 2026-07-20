"""任务日志查询 API (M09 对外接口)。

提供按 task_id / 级别 / 模块筛选的日志查询能力，供前端管理页使用。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import TaskLogResponse
from app.services.task_log_service import get_all_logs, get_task_logs
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/")
def list_logs(
    task_id: int | None = Query(None, description="按任务 ID 过滤"),
    level: str | None = Query(None, description="按日志级别过滤: INFO / WARN / ERROR"),
    log_type: str | None = Query(None, description="按模块过滤: M01 / M02 ..."),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    db: Session = Depends(get_db),
):
    """查询系统日志列表

    支持按 task_id、日志级别、模块名组合筛选。
    """
    try:
        if task_id is not None:
            logs = get_task_logs(db, task_id, limit=limit, level=level, log_type=log_type)
        else:
            logs = get_all_logs(db, limit=limit, level=level, log_type=log_type, task_id=task_id)

        data = [TaskLogResponse.model_validate(log).model_dump(mode="json") for log in logs]
        return success_response(data=data, message=f"共 {len(data)} 条日志")
    except Exception as e:
        return error_response(f"查询日志失败: {e}")


@router.get("/task/{task_id}")
def list_task_logs(
    task_id: int,
    level: str | None = Query(None, description="按日志级别过滤"),
    log_type: str | None = Query(None, description="按模块过滤"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """查询指定任务的日志"""
    try:
        logs = get_task_logs(db, task_id, limit=limit, level=level, log_type=log_type)
        data = [TaskLogResponse.model_validate(log).model_dump(mode="json") for log in logs]
        return success_response(data=data, message=f"任务 {task_id} 共 {len(data)} 条日志")
    except Exception as e:
        return error_response(f"查询任务日志失败: {e}")
