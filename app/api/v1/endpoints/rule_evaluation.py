"""规则评测 API (P3-5)。

提供规则效果评测接口:
  - GET /api/v1/rule-evaluation/             获取所有规则评测数据
  - GET /api/v1/rule-evaluation/summary      获取评测汇总数据
  - GET /api/v1/rule-evaluation/{rule_id}    获取单条规则详细评测
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.rule_evaluator import RuleEvaluator
from app.utils.response import error_response, success_response

router = APIRouter()


@router.get("/")
def get_rule_evaluation(db: Session = Depends(get_db)):
    """获取所有规则的效果评测数据"""
    evaluator = RuleEvaluator(db)
    results = evaluator.evaluate_all()
    return success_response(
        data=results,
        message=f"共 {len(results)} 条规则评测数据",
    )


@router.get("/summary")
def get_evaluation_summary(db: Session = Depends(get_db)):
    """获取规则评测汇总数据（用于仪表盘展示）"""
    evaluator = RuleEvaluator(db)
    summary = evaluator.get_evaluation_summary()
    return success_response(data=summary)


@router.get("/{rule_id}")
def get_rule_detail_evaluation(rule_id: int, db: Session = Depends(get_db)):
    """获取单条规则的详细评测数据（含最近命中证据）"""
    evaluator = RuleEvaluator(db)
    result = evaluator.get_rule_detail(rule_id)
    if not result:
        return error_response(f"规则不存在: {rule_id}", code=404)
    return success_response(data=result)
