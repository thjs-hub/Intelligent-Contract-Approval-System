"""审查报告 API (P3-6)。

提供审查报告生成与导出接口:
  - GET /api/v1/reports/{task_id}/distribution  获取风险分布数据
  - GET /api/v1/reports/{task_id}/pdf           导出 PDF 审查报告
  - GET /api/v1/reports/{task_id}/preview       获取报告预览数据
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ai_review_result import AIReviewResult
from app.models.review_result import ReviewResult
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/{task_id}/distribution")
def get_risk_distribution(task_id: int, db: Session = Depends(get_db)):
    """获取风险分布数据（供前端可视化图表）"""
    service = ReportService(db)
    review_service = ReviewService(db)

    # 获取规则命中
    rule_hits = review_service.list_rule_hits(task_id)

    # 获取 AI 风险项
    ai_record = db.query(AIReviewResult).filter(
        AIReviewResult.task_id == task_id
    ).first()
    ai_risk_items = ai_record.risk_items_json if ai_record else []

    distribution = service.generate_risk_distribution(rule_hits, ai_risk_items)
    return success_response(data=distribution)


@router.get("/{task_id}/pdf")
def export_pdf_report(task_id: int, db: Session = Depends(get_db)):
    """导出 PDF 审查报告

    返回 application/pdf 二进制内容，浏览器直接下载
    """
    service = ReportService(db)

    # 获取所有审查数据
    review_result = db.query(ReviewResult).filter(
        ReviewResult.task_id == task_id
    ).first()
    if not review_result:
        return error_response("无审查结果，无法生成报告", code=404)

    review_service = ReviewService(db)
    rule_hits = review_service.list_rule_hits(task_id)

    ai_record = db.query(AIReviewResult).filter(
        AIReviewResult.task_id == task_id
    ).first()

    risk_distribution = service.generate_risk_distribution(
        rule_hits,
        ai_record.risk_items_json if ai_record else [],
    )

    try:
        pdf_bytes = service.generate_pdf_report(
            task_id=task_id,
            review_result={
                "overall_risk_level": review_result.overall_risk_level,
                "summary_text": review_result.summary_text or "",
                "ai_summary": ai_record.ai_summary if ai_record else "",
                "created_at": (
                    review_result.created_at.isoformat()
                    if review_result.created_at
                    else ""
                ),
                "rule_hits": rule_hits,
            },
            ai_result={
                "risk_items": ai_record.risk_items_json if ai_record else [],
                "overall_assessment": ai_record.overall_assessment if ai_record else "",
                "missing_clauses": ai_record.missing_clauses_json if ai_record else [],
            } if ai_record else None,
            risk_distribution=risk_distribution,
        )
    except ImportError as e:
        return error_response(f"PDF 生成依赖未安装: {e}", code=500)
    except Exception as e:
        return error_response(f"PDF 生成失败: {e}", code=500)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=review_report_{task_id}.pdf"
        },
    )


@router.get("/{task_id}/preview")
def get_report_preview(task_id: int, db: Session = Depends(get_db)):
    """获取报告预览数据（供前端展示）"""
    review_result = db.query(ReviewResult).filter(
        ReviewResult.task_id == task_id
    ).first()
    if not review_result:
        return error_response("无审查结果", code=404)

    review_service = ReviewService(db)
    rule_hits = review_service.list_rule_hits(task_id)

    ai_record = db.query(AIReviewResult).filter(
        AIReviewResult.task_id == task_id
    ).first()

    service = ReportService(db)
    risk_distribution = service.generate_risk_distribution(
        rule_hits,
        ai_record.risk_items_json if ai_record else [],
    )

    # 构造规则结果摘要
    rule_results = []
    rule_id_map = {}
    if rule_hits:
        from app.models.review_rule import ReviewRule

        rules = db.query(ReviewRule).filter(
            ReviewRule.id.in_([h.rule_id for h in rule_hits])
        ).all()
        rule_id_map = {r.id: r for r in rules}

    for hit in rule_hits:
        rule = rule_id_map.get(hit.rule_id)
        if rule:
            rule_results.append({
                "rule_name": rule.rule_name,
                "match_mode": rule.match_mode,
                "risk_level": rule.risk_level,
                "evidence_text": (hit.evidence_text or "")[:200],
                "evidence_position": hit.evidence_position,
                "suggestion_text": rule.suggestion_text,
            })

    data = {
        "task_id": task_id,
        "overall_risk_level": review_result.overall_risk_level,
        "summary_text": review_result.summary_text or "",
        "ai_summary": ai_record.ai_summary if ai_record else "",
        "risk_distribution": risk_distribution,
        "rule_results": rule_results,
        "ai_risk_items": ai_record.risk_items_json if ai_record else [],
        "missing_clauses": ai_record.missing_clauses_json if ai_record else [],
        "ai_assessment": ai_record.overall_assessment if ai_record else "",
        "model_name": ai_record.model_name if ai_record else "",
        "created_at": (
            review_result.created_at.isoformat()
            if review_result.created_at
            else ""
        ),
    }
    return success_response(data=data)
