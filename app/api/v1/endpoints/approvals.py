from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_pending_contract_approvals(limit: int = 10):
    """拉取待处理审批单列表"""
    return {"status": "ok", "message": "待实现", "data": [], "limit": limit}


@router.get("/{instance_id}")
def get_contract_approval(instance_id: str):
    """查询单个审批单详情"""
    return {"status": "ok", "message": "待实现", "data": {"instance_id": instance_id}}
