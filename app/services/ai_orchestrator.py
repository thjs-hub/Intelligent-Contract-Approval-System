"""AI 审查编排服务 — 第三阶段新增。

统一调度规则审查（M06，含 semantic）和 AI 审查（P3-4 LLM），
将两者的结果合并后统一交给 M07 结果管理。

核心职责:
  1. 串联 NLP 解析 → 规则审查 → 语义匹配 → LLM 深度分析 → 报告生成
  2. 将规则命中结果和 AI 风险项合并，计算综合风险等级
  3. 通过配置项控制各 AI 模块的启停（LLM_ENABLED / SEMANTIC_ENABLED 等）
  4. 优雅降级: 任一 AI 模块失败不影响整体流程，降级到可用模块

设计要点:
  - run_full_review 是第三阶段的核心入口，串联所有 AI 能力
  - LLM 审查失败时降级到纯规则审查，不影响核心流程
  - 综合风险等级取规则风险和 AI 风险的最高值
  - AI 高风险项自动加入审批关注点
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.ai_reviewer import LLMReviewer
from app.services.parse_service import ParseService
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.services.task_log_service import log_error, log_info

logger = logging.getLogger("contract_review")


class AIOrchestrator:
    """AI 审查编排器"""

    def __init__(self, db: Session):
        self.db = db

    async def run_full_review(self, task_id: int) -> dict[str, Any]:
        """执行完整的 AI 增强审查流程

        流程:
          1. M06 规则审查（含 semantic 语义匹配，由 RuleMatcher 内部根据
             SEMANTIC_ENABLED 开关决定是否启用）
          2. P3-4 LLM 深度分析（可选，由 LLM_ENABLED 配置控制）
          3. 合并结果 + 计算综合风险等级
          4. 生成 AI 摘要 + 优化回写内容
          5. 返回完整审查结果（由调用方决定是否调用 M07 保存）

        参数:
          task_id: 任务 ID

        返回:
            {
                "rule_hits": [...],          # 规则命中列表（RuleHit 对象）
                "ai_risk_items": [...],      # AI 识别的风险项列表
                "overall_risk_level": "低"|"中"|"高",  # 综合风险等级
                "summary_text": str,         # 摘要文本（优先 AI 摘要）
                "comment_text": str,         # 优化后的回写评论
                "focus_points": [...],       # 审批关注点（含 AI 高风险项）
                "risk_distribution": {...},  # 风险分布数据
                "ai_assessment": str,        # LLM 总体评估
                "review_mode": "rules_only"|"rules_and_ai",  # 审查模式
            }
        """
        # ===== 1. 规则审查（M06 增强，含 semantic） =====
        review_service = ReviewService(self.db)
        rule_result = await review_service.run_contract_rules(task_id)
        rule_hits = rule_result.get("hits", [])
        rule_risk_level = rule_result.get("overall_risk_level", "低")
        focus_points: list[str] = list(rule_result.get("focus_points", []))

        log_info(
            self.db,
            task_id,
            "AI-Orchestrator",
            f"规则审查完成: 命中{len(rule_hits)}条, 风险={rule_risk_level}",
        )

        # ===== 2. LLM 深度分析（可选） =====
        ai_risk_items: list[dict[str, Any]] = []
        ai_summary = ""
        ai_assessment = ""
        review_mode = "rules_only"

        llm_enabled = getattr(settings, "LLM_ENABLED", False)
        if llm_enabled:
            try:
                ai_result = await self._run_llm_review(task_id, rule_result)
                ai_risk_items = ai_result.get("risk_items", [])
                ai_summary = ai_result.get("ai_summary", "")
                ai_assessment = ai_result.get("overall_assessment", "")
                review_mode = "rules_and_ai"

                log_info(
                    self.db,
                    task_id,
                    "AI-Orchestrator",
                    f"LLM审查完成: 识别{len(ai_risk_items)}项风险",
                )
            except Exception as e:
                log_error(
                    self.db,
                    task_id,
                    "AI-Orchestrator",
                    f"LLM审查失败(降级到纯规则): {e}",
                )

        # ===== 3. 合并结果 + 计算综合风险等级 =====
        overall_risk_level = self._merge_risk_levels(rule_risk_level, ai_risk_items)

        # 合并 AI 高风险项到关注点
        for item in ai_risk_items:
            if isinstance(item, dict) and item.get("risk_level") == "高":
                focus_points.append(
                    f"【AI高风险】{item.get('risk_type', '')}："
                    f"{item.get('suggestion', '')}"
                )

        # ===== 4. 生成 AI 摘要 =====
        if ai_summary:
            summary_text = ai_summary
        else:
            summary_text = review_service._generate_summary(
                rule_hits, overall_risk_level, focus_points
            )

        # ===== 5. 生成优化回写内容 =====
        report_service = ReportService(self.db)
        comment_text = report_service.generate_optimized_comment(
            overall_risk_level=overall_risk_level,
            ai_summary=ai_summary,
            rule_hits=rule_hits,
            ai_risk_items=ai_risk_items,
            focus_points=focus_points,
        )

        # 风险分布
        risk_distribution = report_service.generate_risk_distribution(
            rule_hits, ai_risk_items
        )

        log_info(
            self.db,
            task_id,
            "AI-Orchestrator",
            f"完整审查完成: 规则{len(rule_hits)}条 + "
            f"AI{len(ai_risk_items)}项, 综合风险={overall_risk_level}",
        )

        return {
            "rule_hits": rule_hits,
            "ai_risk_items": ai_risk_items,
            "overall_risk_level": overall_risk_level,
            "summary_text": summary_text,
            "comment_text": comment_text,
            "focus_points": focus_points,
            "risk_distribution": risk_distribution,
            "ai_assessment": ai_assessment,
            "review_mode": review_mode,
        }

    async def _run_llm_review(
        self, task_id: int, rule_result: dict[str, Any]
    ) -> dict[str, Any]:
        """执行 LLM 审查

        参数:
          task_id: 任务 ID
          rule_result: 规则审查结果（作为 LLM 上下文）

        返回:
          LLM 审查结果（含 risk_items, ai_summary, overall_assessment）
        """
        parse_service = ParseService(self.db)
        parse_record = parse_service.get_parse_result(task_id)
        contract_text = parse_service.get_full_text(task_id)

        reviewer = LLMReviewer()
        ai_result = await reviewer.deep_analysis(
            contract_text=contract_text,
            parse_result={
                "basic_info": (parse_record.basic_info_json if parse_record else None) or {},
                "clause_info": (parse_record.clause_info_json if parse_record else None) or {},
            },
            rule_review_result=rule_result,
        )

        # 生成 AI 摘要
        ai_summary = await reviewer.generate_summary(
            rule_hits=rule_result.get("hits", []),
            ai_risk_items=ai_result.get("risk_items", []),
            overall_risk_level=rule_result.get("overall_risk_level", "低"),
        )
        ai_result["ai_summary"] = ai_summary

        # 持久化 AI 结果
        self._save_ai_result(task_id, ai_result)

        return ai_result

    def _merge_risk_levels(
        self, rule_risk: str, ai_risk_items: list[dict[str, Any]]
    ) -> str:
        """合并规则风险等级和 AI 风险等级

        规则:
          - 任一来源有高风险 → "高"
          - 任一来源有中风险 → "中"
          - 全部为低 → "低"
        """
        levels = {rule_risk}
        for item in ai_risk_items:
            if isinstance(item, dict):
                levels.add(item.get("risk_level", "中"))

        if "高" in levels:
            return "高"
        elif "中" in levels:
            return "中"
        return "低"

    def _save_ai_result(self, task_id: int, ai_result: dict[str, Any]) -> None:
        """持久化 AI 审查结果到 ai_review_results 表"""
        from app.models.ai_review_result import AIReviewResult

        existing = self.db.query(AIReviewResult).filter(
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
            self.db.add(record)

        self.db.commit()
