"""AI 审查编排 API。

提供 AI 增强审查的统一编排入口:
  - POST /api/v1/orchestrate/{task_id}/full-review  执行完整 AI 增强审查
  - GET  /api/v1/orchestrate/config                 获取 AI 配置开关状态
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.ai_orchestrator import AIOrchestrator
from app.services.result_service import ResultService
from app.services.task_log_service import log_error
from app.utils.response import error_response, success_response

router = APIRouter()


@router.post("/{task_id}/full-review")
async def run_full_review(task_id: int, db: Session = Depends(get_db)):
    """执行完整的 AI 增强审查（规则 + 语义 + LLM + 报告）

    这是第三阶段的核心入口，串联所有 AI 能力。
    根据配置开关自动决定启用哪些 AI 模块，关闭的模块自动降级。

    流程:
      1. AIOrchestrator.run_full_review 编排规则审查 + LLM 审查 + 合并结果
      2. ResultService.save_review_result_with_ai 保存含 AI 内容的审查结果
      3. 返回完整审查结果
    """
    try:
        orchestrator = AIOrchestrator(db)
        result = await orchestrator.run_full_review(task_id)

        # 保存到 M07（含 AI 审查内容）
        result_service = ResultService(db)
        result_service.save_review_result_with_ai(
            task_id=task_id,
            overall_risk_level=result["overall_risk_level"],
            focus_points=result["focus_points"],
            rule_hits=result["rule_hits"],
            ai_risk_items=result["ai_risk_items"],
            ai_summary=result["summary_text"],
        )

        # 序列化 rule_hits 用于响应
        from app.schemas.rule import RuleHitResponse

        hits_data = [
            RuleHitResponse.model_validate(h).model_dump(mode="json")
            for h in result["rule_hits"]
        ]

        response_data = {
            "task_id": task_id,
            "overall_risk_level": result["overall_risk_level"],
            "summary_text": result["summary_text"],
            "comment_text": result["comment_text"],
            "focus_points": result["focus_points"],
            "risk_distribution": result["risk_distribution"],
            "ai_assessment": result["ai_assessment"],
            "review_mode": result["review_mode"],
            "rule_hits": hits_data,
            "rule_hit_count": len(hits_data),
            "ai_risk_items": result["ai_risk_items"],
            "ai_risk_count": len(result["ai_risk_items"]),
        }

        return success_response(
            data=response_data,
            message="AI 增强审查完成",
        )

    except Exception as e:
        log_error(db, task_id, "AI-Orchestrator", f"完整审查失败: {e}")
        return error_response(f"AI 增强审查失败: {e}")


@router.get("/config")
def get_ai_config():
    """获取 AI 配置开关状态（供前端展示当前启用的 AI 能力）"""
    config = {
        "extractor_type": getattr(settings, "EXTRACTOR_TYPE", "regex"),
        "nlp_extractor_enabled": getattr(settings, "NLP_EXTRACTOR_ENABLED", False),
        "ocr_use_layout": getattr(settings, "OCR_USE_LAYOUT", False),
        "ocr_table_recognition": getattr(settings, "OCR_TABLE_RECOGNITION", False),
        "semantic_enabled": getattr(settings, "SEMANTIC_ENABLED", False),
        "semantic_threshold": getattr(settings, "SEMANTIC_THRESHOLD", 0.75),
        "llm_enabled": getattr(settings, "LLM_ENABLED", False),
        "llm_model": getattr(settings, "LLM_MODEL", "qwen-plus"),
        "llm_endpoint_configured": bool(getattr(settings, "LLM_ENDPOINT", "")),
        "ai_review_enabled": getattr(settings, "AI_REVIEW_ENABLED", False),
        "ai_report_enhance": getattr(settings, "AI_REPORT_ENHANCE", False),
    }
    return success_response(data=config)
