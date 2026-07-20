"""审查结果管理 API (M07)。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.result import ReviewResultResponse
from app.services.result_service import ResultService
from app.services.review_service import ReviewService
from app.utils.response import error_response, success_response

router = APIRouter()


class SaveReviewRequest(BaseModel):
    """保存审查结果请求

    当 auto_run_rules=True 时，overall_risk_level/summary_text/focus_points
    会从规则审查结果中自动获取，请求体中无需提供。
    """

    task_id: int = Field(..., description="任务 ID")
    overall_risk_level: str | None = Field(None, description="总体风险等级: 低/中/高（auto_run_rules=True 时可省略）")
    summary_text: str | None = Field(None, description="审查摘要（auto_run_rules=True 时可省略）")
    focus_points: list[str] | None = Field(None, description="审批关注点（auto_run_rules=True 时可省略）")
    auto_run_rules: bool = Field(
        True, description="是否自动执行规则审查（若尚未执行）"
    )


@router.post("/save")
async def save_review_result(
    req: SaveReviewRequest,
    db: Session = Depends(get_db),
):
    """接口: save_review_result(case_id, overall_risk_level, summary_text,
                                focus_points_json, comment_text)

    保存审查结果。当 auto_run_rules=True 且任务尚无命中记录时，
    会先自动触发 M06 规则审查。
    """
    try:
        review_service = ReviewService(db)
        result_service = ResultService(db)

        # 若启用自动审查，先执行规则审查获取 hits
        if req.auto_run_rules:
            review_result = await review_service.run_contract_rules(req.task_id)
            hits = review_result["hits"]
            overall_risk = review_result["overall_risk_level"]
            summary = review_result["summary_text"]
            focus = review_result["focus_points"]
        else:
            # 直接使用请求参数（若未提供则使用默认值）
            hits = review_service.list_rule_hits(req.task_id)
            overall_risk = req.overall_risk_level or "低"
            summary = req.summary_text or ""
            focus = req.focus_points or []

        # 保存结果
        result = result_service.save_review_result(
            task_id=req.task_id,
            overall_risk_level=overall_risk,
            summary_text=summary,
            focus_points=focus,
            hits=hits,
        )
        data = ReviewResultResponse.model_validate(result).model_dump(mode="json")
        return success_response(data=data, message="审查结果已保存")
    except ValueError as e:
        return error_response(str(e), code=400)
    except Exception as e:
        return error_response(f"保存审查结果失败: {e}")


@router.get("/{task_id}")
def get_review_result(
    task_id: int,
    db: Session = Depends(get_db),
):
    """查询任务的审查结果"""
    service = ResultService(db)
    result = service.get_review_result(task_id)
    if not result:
        return error_response(f"任务 {task_id} 暂无审查结果", code=404)
    data = ReviewResultResponse.model_validate(result).model_dump(mode="json")
    return success_response(data=data)
