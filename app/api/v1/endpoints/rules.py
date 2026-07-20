from fastapi import APIRouter

router = APIRouter()


@router.post("/run/{case_id}")
def run_contract_rules(case_id: str):
    """执行规则审查并返回命中结果和风险结论"""
    return {
        "status": "ok",
        "message": "待实现",
        "data": {
            "case_id": case_id,
            "overall_risk_level": "低",
            "hits": [],
            "summary_text": "",
            "focus_points": [],
        },
    }


@router.get("/")
def list_review_rules():
    """获取审查规则列表"""
    return {"status": "ok", "data": []}
