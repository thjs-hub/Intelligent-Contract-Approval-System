"""AI 智能审查 API (P3-4)。

提供 LLM 智能审查的触发与查询接口:
  - POST /api/v1/ai-review/trigger/{task_id}  触发 AI 审查
  - GET  /api/v1/ai-review/results/{task_id}  获取 AI 审查结果
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.ai_review_result import AIReviewResult
from app.services.ai_reviewer import LLMReviewer
from app.services.parse_service import ParseService
from app.services.review_service import ReviewService
from app.services.task_log_service import log_error, log_info
from app.utils.response import error_response, success_response

router = APIRouter()


@router.post("/trigger/{task_id}")
async def trigger_ai_review(task_id: int, db: Session = Depends(get_db)):
    """触发 LLM 智能审查

    流程:
      1. 检查 LLM 是否启用（LLM_ENABLED）
      2. 获取 M04 解析结果（必须先完成文档解析）
      3. 获取 M06 规则审查结果作为 LLM 上下文
      4. 调用 LLM 深度分析
      5. 生成 AI 摘要
      6. 持久化到 ai_review_results 表
    """
    # 1. 检查 LLM 是否启用
    if not getattr(settings, "LLM_ENABLED", False):
        return error_response(
            "LLM 智能审查未启用，请在配置中开启 LLM_ENABLED",
            code=400,
        )

    try:
        # 2. 获取解析结果
        parse_service = ParseService(db)
        parse_record = parse_service.get_parse_result(task_id)
        if not parse_record or parse_record.parse_status != "success":
            return error_response(
                "请先完成文档解析后再执行 AI 审查",
                code=400,
            )

        # 3. 获取规则审查结果（作为 LLM 上下文）
        review_service = ReviewService(db)
        rule_result = await review_service.run_contract_rules(task_id)

        # 4. 获取合同全文
        contract_text = parse_service.get_full_text(task_id)

        # 5. 调用 LLM 深度分析
        reviewer = LLMReviewer()
        ai_result = await reviewer.deep_analysis(
            contract_text=contract_text,
            parse_result={
                "basic_info": parse_record.basic_info_json or {},
                "clause_info": parse_record.clause_info_json or {},
            },
            rule_review_result=rule_result,
        )

        # 6. 生成 AI 摘要
        ai_summary = await reviewer.generate_summary(
            rule_hits=rule_result.get("hits", []),
            ai_risk_items=ai_result.get("risk_items", []),
            overall_risk_level=rule_result.get("overall_risk_level", "低"),
        )
        ai_result["ai_summary"] = ai_summary

        # 7. 持久化
        _save_ai_review_result(db, task_id, ai_result)

        log_info(
            db,
            task_id,
            "P3-4",
            f"LLM审查完成: 识别{len(ai_result.get('risk_items', []))}项风险",
        )

        return success_response(
            data=_format_ai_result(ai_result),
            message="AI 智能审查完成",
        )

    except Exception as e:
        log_error(db, task_id, "P3-4", f"LLM 审查失败: {e}")
        return error_response(f"AI 审查失败: {e}")


@router.get("/results/{task_id}")
def get_ai_review_result(task_id: int, db: Session = Depends(get_db)):
    """获取 AI 审查结果"""
    record = db.query(AIReviewResult).filter(
        AIReviewResult.task_id == task_id
    ).first()
    if not record:
        return error_response("尚无 AI 审查结果", code=404)

    data = {
        "id": record.id,
        "task_id": record.task_id,
        "risk_items": record.risk_items_json or [],
        "overall_assessment": record.overall_assessment or "",
        "missing_clauses": record.missing_clauses_json or [],
        "ai_summary": record.ai_summary or "",
        "model_name": record.model_name or "",
        "token_usage": record.token_usage or 0,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }
    return success_response(data=data)


def _save_ai_review_result(db: Session, task_id: int, ai_result: dict) -> None:
    """保存或更新 AI 审查结果"""
    existing = db.query(AIReviewResult).filter(
        AIReviewResult.task_id == task_id
    ).first()

    if existing:
        existing.risk_items_json = ai_result.get("risk_items", [])
        existing.overall_assessment = ai_result.get("overall_assessment", "")
        existing.missing_clauses_json = ai_result.get("missing_clauses", [])
        existing.ai_summary = ai_result.get("ai_summary", "")
        existing.model_name = ai_result.get("model", "")
    else:
        record = AIReviewResult(
            task_id=task_id,
            risk_items_json=ai_result.get("risk_items", []),
            overall_assessment=ai_result.get("overall_assessment", ""),
            missing_clauses_json=ai_result.get("missing_clauses", []),
            ai_summary=ai_result.get("ai_summary", ""),
            model_name=ai_result.get("model", ""),
        )
        db.add(record)

    db.commit()


def _format_ai_result(ai_result: dict) -> dict:
    """格式化 AI 审查结果用于 API 响应"""
    return {
        "risk_items": ai_result.get("risk_items", []),
        "overall_assessment": ai_result.get("overall_assessment", ""),
        "missing_clauses": ai_result.get("missing_clauses", []),
        "ai_summary": ai_result.get("ai_summary", ""),
        "model": ai_result.get("model", ""),
        "error": ai_result.get("error"),
    }
