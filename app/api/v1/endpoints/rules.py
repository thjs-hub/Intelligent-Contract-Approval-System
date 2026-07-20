"""规则审查与规则管理 API (M06)。

提供两类接口:
  - 规则 CRUD: GET/POST/PUT/DELETE /rules/
  - 规则执行: POST /rules/run/{task_id}
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.review_rule import ReviewRule
from app.schemas.rule import (
    ReviewRuleCreate,
    ReviewRuleResponse,
    ReviewRuleUpdate,
    RuleHitResponse,
)
from app.services.review_service import ReviewService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/")
def list_review_rules(db: Session = Depends(get_db)):
    """获取审查规则列表"""
    rules = list(
        db.scalars(select(ReviewRule).order_by(ReviewRule.rule_code.asc()))
    )
    data = [
        ReviewRuleResponse.model_validate(r).model_dump(mode="json") for r in rules
    ]
    return success_response(data=data, message=f"共 {len(data)} 条规则")


@router.post("/")
def create_review_rule(
    rule: ReviewRuleCreate,
    db: Session = Depends(get_db),
):
    """新增审查规则"""
    # 检查 rule_code 唯一性
    existing = db.scalar(select(ReviewRule).where(ReviewRule.rule_code == rule.rule_code))
    if existing:
        return error_response(f"规则编码已存在: {rule.rule_code}", code=400)

    new_rule = ReviewRule(
        rule_code=rule.rule_code,
        rule_name=rule.rule_name,
        risk_level=rule.risk_level,
        rule_status="enabled",
        match_mode=rule.match_mode,
        match_text=rule.match_text,
        suggestion_text=rule.suggestion_text,
    )
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    data = ReviewRuleResponse.model_validate(new_rule).model_dump(mode="json")
    return success_response(data=data, message="规则创建成功")


@router.get("/{rule_id}")
def get_review_rule(
    rule_id: int,
    db: Session = Depends(get_db),
):
    """查询单条规则"""
    rule = db.get(ReviewRule, rule_id)
    if not rule:
        return error_response(f"规则不存在: {rule_id}", code=404)
    data = ReviewRuleResponse.model_validate(rule).model_dump(mode="json")
    return success_response(data=data)


@router.put("/{rule_id}")
def update_review_rule(
    rule_id: int,
    rule_update: ReviewRuleUpdate,
    db: Session = Depends(get_db),
):
    """更新审查规则"""
    rule = db.get(ReviewRule, rule_id)
    if not rule:
        return error_response(f"规则不存在: {rule_id}", code=404)

    # 仅更新非 None 字段
    update_data = rule_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    db.commit()
    db.refresh(rule)
    data = ReviewRuleResponse.model_validate(rule).model_dump(mode="json")
    return success_response(data=data, message="规则更新成功")


@router.delete("/{rule_id}")
def delete_review_rule(
    rule_id: int,
    db: Session = Depends(get_db),
):
    """删除审查规则"""
    rule = db.get(ReviewRule, rule_id)
    if not rule:
        return error_response(f"规则不存在: {rule_id}", code=404)

    db.delete(rule)
    db.commit()
    return success_response(message="规则删除成功")


@router.put("/{rule_id}/toggle")
def toggle_review_rule(
    rule_id: int,
    enabled: bool,
    db: Session = Depends(get_db),
):
    """启用/禁用规则"""
    rule = db.get(ReviewRule, rule_id)
    if not rule:
        return error_response(f"规则不存在: {rule_id}", code=404)

    rule.rule_status = "enabled" if enabled else "disabled"
    db.commit()
    db.refresh(rule)
    data = ReviewRuleResponse.model_validate(rule).model_dump(mode="json")
    return success_response(data=data, message=f"规则已{'启用' if enabled else '禁用'}")


@router.post("/run/{task_id}")
async def run_contract_rules(
    task_id: int,
    db: Session = Depends(get_db),
):
    """接口: run_contract_rules(case_id)

    执行规则审查主流程，返回命中结果和风险结论。
    """
    service = ReviewService(db)
    try:
        result = await service.run_contract_rules(task_id)
        # 序列化 hits 列表
        hits_data = [
            RuleHitResponse.model_validate(h).model_dump(mode="json")
            for h in result["hits"]
        ]
        data = {
            "task_id": result["task_id"],
            "overall_risk_level": result["overall_risk_level"],
            "summary_text": result["summary_text"],
            "focus_points": result["focus_points"],
            "hits": hits_data,
            "hit_count": len(hits_data),
        }
        return success_response(data=data, message="规则审查完成")
    except Exception as e:
        return error_response(f"规则审查失败: {e}")


@router.get("/hits/{task_id}")
def list_rule_hits(
    task_id: int,
    db: Session = Depends(get_db),
):
    """查询任务的规则命中记录"""
    service = ReviewService(db)
    hits = service.list_rule_hits(task_id)
    data = [
        RuleHitResponse.model_validate(h).model_dump(mode="json") for h in hits
    ]
    return success_response(data=data, message=f"共 {len(data)} 条命中记录")
