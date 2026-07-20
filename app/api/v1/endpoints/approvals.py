"""审批待办接入 API (M01)。

提供两条核心 API:
  - GET /approvals/        拉取待处理审批单列表（触发同步 + 去重）
  - GET /approvals/{code}  查询单个审批单详情（本地数据库）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import ApprovalTaskResponse
from app.services.approval_service import ApprovalService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/")
async def list_approvals(
    limit: int = Query(20, ge=1, le=100, description="拉取条数上限"),
    sync: bool = Query(True, description="是否触发从外部审批系统同步"),
    db: Session = Depends(get_db),
):
    """接口: list_pending_contract_approvals(limit)

    拉取待处理审批单列表。当 sync=true 时，会主动调用外部审批系统适配器
    拉取最新审批单并按 approval_code 去重后入库。
    """
    service = ApprovalService(db)
    try:
        if sync:
            # 触发外部同步 + 去重
            tasks = await service.list_pending_approvals(limit)
        else:
            # 仅查询本地已存储的任务
            tasks = service.list_local_tasks(limit=limit)

        data = [
            ApprovalTaskResponse.model_validate(t).model_dump(mode="json") for t in tasks
        ]
        return success_response(
            data=data,
            message=f"已同步 {len(data)} 条审批单" if sync else f"共 {len(data)} 条审批单",
        )
    except Exception as e:
        return error_response(f"拉取审批单失败: {e}")


@router.get("/{approval_code}")
async def get_approval(
    approval_code: str,
    db: Session = Depends(get_db),
):
    """接口: get_contract_approval(instance_id)

    查询单个审批单详情（从本地数据库读取）。
    """
    service = ApprovalService(db)
    task = service.get_approval_detail(approval_code)
    if not task:
        return error_response(f"审批单不存在: {approval_code}", code=404)
    data = ApprovalTaskResponse.model_validate(task).model_dump(mode="json")
    return success_response(data=data)
