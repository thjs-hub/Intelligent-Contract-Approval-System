"""规则审查服务 (M06)。

主入口: run_contract_rules(task_id)
流程:
  1. 更新任务状态为 reviewing
  2. 获取 M04 解析结果
  3. 调用 RuleMatcher 执行规则匹配
  4. 汇总风险等级（含高 → 高，含中 → 中，无命中 → 低）
  5. 生成摘要文本和审批关注点
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contract_parse import ContractParse
from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.services.block_handler import BlockHandler
from app.services.rule_engine import RuleMatcher
from app.services.task_log_service import log_error, log_info


class ReviewService:
    """规则审查服务"""

    def __init__(self, db: Session):
        self.db = db

    async def run_contract_rules(self, task_id: int) -> dict:
        """接口: run_contract_rules(case_id)

        执行规则审查主流程。

        参数:
          task_id: 任务 ID

        返回:
          {
            "task_id": int,
            "hits": list[RuleHit],
            "overall_risk_level": "低" | "中" | "高",
            "summary_text": str,
            "focus_points": list[str],
          }
        """
        # 1. 更新任务状态
        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task:
            task.task_status = "reviewing"
        self.db.flush()

        # 2. 获取解析结果（要求 parse_status=success）
        parse_record = self.db.scalar(
            select(ContractParse)
            .where(
                ContractParse.task_id == task_id,
                ContractParse.parse_status == "success",
            )
        )

        if not parse_record:
            log_error(self.db, task_id, "M06", "无可用的解析结果，请先执行 M04 解析")
            BlockHandler.trigger_block(
                self.db, task_id, reason="无可用的解析结果", module="M06"
            )
            return {
                "task_id": task_id,
                "hits": [],
                "overall_risk_level": "低",
                "summary_text": "无可用的解析结果，无法执行规则审查",
                "focus_points": [],
            }

        # 3. 执行规则匹配
        matcher = RuleMatcher(self.db)
        hits, focus_points = matcher.match_all(
            task_id=task_id,
            basic_info=parse_record.basic_info_json or {},
            clause_info=parse_record.clause_info_json or {},
        )

        # 4. 汇总风险等级
        overall_risk_level = self._calculate_overall_risk(hits)

        # 5. 生成摘要
        summary_text = self._generate_summary(hits, overall_risk_level, focus_points)

        log_info(
            self.db,
            task_id,
            "M06",
            f"规则审查完成: 命中 {len(hits)} 条规则, 总风险等级={overall_risk_level}",
        )

        self.db.commit()

        return {
            "task_id": task_id,
            "hits": hits,
            "overall_risk_level": overall_risk_level,
            "summary_text": summary_text,
            "focus_points": focus_points,
        }

    def _calculate_overall_risk(self, hits: list[RuleHit]) -> str:
        """基于命中规则的风险等级汇总总体风险

        规则:
          - 含任一高风险 → "高"
          - 含任一中风险 → "中"
          - 无命中或仅低风险 → "低"
        """
        if not hits:
            return "低"

        rule_ids = [h.rule_id for h in hits]
        rules = list(
            self.db.scalars(select(ReviewRule).where(ReviewRule.id.in_(rule_ids)))
        )

        has_high = any(r.risk_level == "高" for r in rules)
        has_medium = any(r.risk_level == "中" for r in rules)

        if has_high:
            return "高"
        elif has_medium:
            return "中"
        return "低"

    def _generate_summary(
        self,
        hits: list[RuleHit],
        overall_risk: str,
        focus_points: list[str],
    ) -> str:
        """生成审查摘要文本"""
        cnt = len(hits)
        if cnt == 0:
            return "经审查，该合同未发现明显风险项。"
        high_count = len(focus_points)
        return (
            f"经审查，该合同共发现 {cnt} 项风险点，总体风险等级为{overall_risk}。"
            f"其中高风险关注点 {high_count} 项，请重点审查。"
        )

    def list_rule_hits(self, task_id: int) -> list[RuleHit]:
        """查询任务的规则命中记录"""
        stmt = (
            select(RuleHit)
            .where(RuleHit.task_id == task_id)
            .order_by(RuleHit.created_at.asc())
        )
        return list(self.db.scalars(stmt))

    def get_review_summary(self, task_id: int) -> Optional[dict]:
        """获取审查结果摘要（不重新执行规则，从已保存数据查询）"""
        hits = self.list_rule_hits(task_id)
        if not hits:
            return None
        overall_risk = self._calculate_overall_risk(hits)
        return {
            "task_id": task_id,
            "hits": hits,
            "overall_risk_level": overall_risk,
            "hit_count": len(hits),
        }
