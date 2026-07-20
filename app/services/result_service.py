"""审查结果管理服务 (M07)。

主入口: save_review_result(task_id, overall_risk_level, summary_text, focus_points, hits)
职责:
  1. 生成格式化的回写评论文本（按需求方规定的输出格式）
  2. 持久化审查结果到 review_results 表（已存在则更新）
  3. 更新任务状态: task_status → done, write_status → not_written
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_result import ReviewResult
from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.services.task_log_service import log_info


class ResultService:
    """审查结果管理服务"""

    def __init__(self, db: Session):
        self.db = db

    def save_review_result(
        self,
        task_id: int,
        overall_risk_level: str,
        summary_text: str,
        focus_points: list[str],
        hits: list[RuleHit],
    ) -> ReviewResult:
        """接口: save_review_result(case_id, overall_risk_level, summary_text,
                                    focus_points_json, comment_text)

        保存审查结果 + 生成回写文本。

        参数:
          task_id: 任务 ID
          overall_risk_level: 总体风险等级 ("低"/"中"/"高")
          summary_text: 审查摘要文本
          focus_points: 审批关注点列表
          hits: 规则命中记录列表

        返回:
          ReviewResult 对象
        """
        # 1. 生成回写评论文本
        comment_text = self._generate_comment_text(
            overall_risk_level, summary_text, focus_points, hits
        )

        # 2. 查找已有结果（已存在则更新）
        existing = self.db.scalar(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )

        if existing:
            existing.overall_risk_level = overall_risk_level
            existing.summary_text = summary_text
            existing.focus_points_json = focus_points
            existing.comment_text = comment_text
            result = existing
        else:
            result = ReviewResult(
                task_id=task_id,
                overall_risk_level=overall_risk_level,
                summary_text=summary_text,
                focus_points_json=focus_points,
                comment_text=comment_text,
            )
            self.db.add(result)

        # 3. 更新任务状态: 审查完成，等待回写
        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task:
            task.task_status = "done"
            task.write_status = "not_written"

        self.db.commit()
        log_info(
            self.db,
            task_id,
            "M07",
            f"审查结果已保存, 风险等级: {overall_risk_level}, 命中 {len(hits)} 条",
        )
        return result

    def _generate_comment_text(
        self,
        overall_risk_level: str,
        summary_text: str,
        focus_points: list[str],
        hits: list[RuleHit],
    ) -> str:
        """生成回写评论内容

        格式规范:
          【智能审查意见】
          总风险等级：高

          审查摘要：...

          风险事项：
          1. 【高风险】预付款比例过高：...
          2. 【中风险】付款周期过长：...

          审批关注点：
          - 请确认预付款比例是否合理
          - ...

          ——以上由智能合同审查系统自动生成，仅供参考——
        """
        # 获取每条命中的规则信息（名称、风险等级、建议）
        rule_id_map = self._get_rule_map([h.rule_id for h in hits])

        lines = [
            "【智能审查意见】",
            f"总风险等级：{overall_risk_level}",
            "",
            f"审查摘要：{summary_text}",
        ]

        # 风险事项列表
        if hits:
            lines.append("")
            lines.append("风险事项：")
            for i, hit in enumerate(hits, 1):
                rule = rule_id_map.get(hit.rule_id)
                if rule:
                    lines.append(
                        f"{i}. 【{rule.risk_level}风险】{rule.rule_name}：{rule.suggestion_text}"
                    )

        # 审批关注点列表
        if focus_points:
            lines.append("")
            lines.append("审批关注点：")
            for point in focus_points:
                lines.append(f"- {point}")

        lines.append("")
        lines.append("——以上由智能合同审查系统自动生成，仅供参考——")

        return "\n".join(lines)

    def _get_rule_map(self, rule_ids: list[int]) -> dict[int, ReviewRule]:
        """批量查询规则并构造 id -> rule 映射"""
        if not rule_ids:
            return {}
        rules = list(
            self.db.scalars(select(ReviewRule).where(ReviewRule.id.in_(rule_ids)))
        )
        return {r.id: r for r in rules}

    def get_review_result(self, task_id: int) -> Optional[ReviewResult]:
        """查询任务的审查结果"""
        return self.db.scalar(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )
