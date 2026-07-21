"""审查结果管理服务 (M07)。

主入口: save_review_result(task_id, overall_risk_level, summary_text, focus_points, hits)
职责:
  1. 生成格式化的回写评论文本（按需求方规定的输出格式）
  2. 持久化审查结果到 review_results 表（已存在则更新）
  3. 更新任务状态: task_status → done, write_status → not_written

第三阶段增强 (P3-6):
  - save_review_result_with_ai: 保存含 AI 审查内容的结果
    使用 ReportService.generate_optimized_comment 生成优化回写文本
    摘要优先使用 AI 摘要，无则降级到模板摘要
"""

from typing import Any, Optional

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

    # ===== 第三阶段新增 — 含 AI 审查内容的结果保存 =====
    def save_review_result_with_ai(
        self,
        task_id: int,
        overall_risk_level: str,
        focus_points: list[str],
        rule_hits: list[RuleHit],
        ai_risk_items: list[dict[str, Any]] | None = None,
        ai_summary: str | None = None,
    ) -> ReviewResult:
        """第三阶段增强: 保存审查结果（含 AI 审查内容）

        相比 save_review_result:
          1. 使用 ReportService.generate_optimized_comment 生成优化回写评论
             （包含规则命中风险 + AI 深度分析风险 + 缺失条款）
          2. 摘要优先使用 AI 摘要，无则降级到模板摘要

        参数:
          task_id: 任务 ID
          overall_risk_level: 总体风险等级（合并规则+AI后的综合等级）
          focus_points: 审批关注点列表
          rule_hits: 规则命中记录列表
          ai_risk_items: AI 识别的风险项列表（字典），可选
          ai_summary: AI 生成的审查摘要，可选

        返回:
          ReviewResult 对象
        """
        from app.services.report_service import ReportService

        report_service = ReportService(self.db)

        # 1. 生成优化后的回写评论
        comment_text = report_service.generate_optimized_comment(
            overall_risk_level=overall_risk_level,
            ai_summary=ai_summary or "",
            rule_hits=rule_hits,
            ai_risk_items=ai_risk_items or [],
            focus_points=focus_points,
        )

        # 2. 摘要使用 AI 摘要（有则用 AI，无则用模板）
        if ai_summary:
            summary_text = ai_summary
        else:
            summary_text = self._generate_summary_text(
                rule_hits, overall_risk_level, focus_points
            )

        # 3. 查找已有结果（已存在则更新）
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

        # 4. 更新任务状态
        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task:
            task.task_status = "done"
            task.write_status = "not_written"

        self.db.commit()
        log_info(
            self.db,
            task_id,
            "M07",
            f"AI 增强审查结果已保存, 综合风险: {overall_risk_level}, "
            f"规则命中 {len(rule_hits)} 条, AI 风险 {len(ai_risk_items or [])} 项",
        )
        return result

    def _generate_summary_text(
        self,
        hits: list[RuleHit],
        overall_risk: str,
        focus_points: list[str],
    ) -> str:
        """生成模板摘要文本（AI 摘要不可用时的降级方案）"""
        cnt = len(hits)
        if cnt == 0:
            return "经审查，该合同未发现明显风险项。"
        high_count = len(focus_points)
        return (
            f"经审查，该合同共发现 {cnt} 项风险点，总体风险等级为{overall_risk}。"
            f"其中高风险关注点 {high_count} 项，请重点审查。"
        )

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
