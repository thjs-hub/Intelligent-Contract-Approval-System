from fastapi import APIRouter

router = APIRouter()


@router.post("/save")
def save_review_result(
    case_id: str,
    overall_risk_level: str,
    summary_text: str,
    focus_points_json: str = "[]",
    comment_text: str = "",
):
    """保存审查结果"""
    return {
        "status": "ok",
        "message": "待实现",
        "data": {
            "case_id": case_id,
            "overall_risk_level": overall_risk_level,
            "summary_text": summary_text,
        },
    }
