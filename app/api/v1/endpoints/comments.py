from fastapi import APIRouter

router = APIRouter()


@router.post("/write/{instance_id}")
def write_approval_comment(instance_id: str, review_id: int):
    """将审查意见写回审批评论区"""
    return {
        "status": "ok",
        "message": "待实现",
        "data": {"instance_id": instance_id, "review_id": review_id, "write_status": "not_written"},
    }
