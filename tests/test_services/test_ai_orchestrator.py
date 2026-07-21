"""AI 审查编排服务单元测试。

测试 AIOrchestrator 的核心功能:
  - run_full_review 完整流程（规则审查 + LLM 审查 + 合并）
  - _merge_risk_levels 风险等级合并
  - LLM 禁用时的降级行为
  - LLM 失败时的降级行为
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.contract_parse import ContractParse
from app.models.review_rule import ReviewRule
from app.models.task import ApprovalTask
from app.services.ai_orchestrator import AIOrchestrator


def _create_task_with_parse(db_session, code: str = "ORCH-001"):
    """创建带解析结果的任务"""
    task = ApprovalTask(approval_code=code, approval_title="编排测试任务")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    parse_record = ContractParse(
        task_id=task.id,
        parse_status="success",
        basic_info_json={
            "contract_amount": {"source_text": "合同金额：100万"},
        },
        clause_info_json={
            "breach_clause": {"source_text": "违约金按合同金额10%收取"},
        },
    )
    db_session.add(parse_record)
    db_session.commit()
    return task, parse_record


def _seed_rule(db_session):
    """创建测试规则"""
    rule = ReviewRule(
        rule_code="R-ORCH-001",
        rule_name="违约责任规则",
        risk_level="高",
        rule_status="enabled",
        match_mode="keyword",
        match_text="违约金",
        suggestion_text="请检查违约责任条款。",
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


@pytest.fixture
def orchestrator(db_session):
    """AIOrchestrator 实例"""
    return AIOrchestrator(db_session)


class TestMergeRiskLevels:
    """_merge_risk_levels 测试"""

    def test_rule_high_ai_high_returns_high(self, orchestrator):
        """规则高 + AI 高 → 高"""
        result = orchestrator._merge_risk_levels("高", [{"risk_level": "高"}])
        assert result == "高"

    def test_rule_medium_ai_high_returns_high(self, orchestrator):
        """规则中 + AI 高 → 高"""
        result = orchestrator._merge_risk_levels("中", [{"risk_level": "高"}])
        assert result == "高"

    def test_rule_low_ai_low_returns_low(self, orchestrator):
        """规则低 + AI 低 → 低"""
        result = orchestrator._merge_risk_levels("低", [{"risk_level": "低"}])
        assert result == "低"

    def test_rule_medium_no_ai_returns_medium(self, orchestrator):
        """规则中 + 无 AI → 中"""
        result = orchestrator._merge_risk_levels("中", [])
        assert result == "中"

    def test_rule_low_ai_medium_returns_medium(self, orchestrator):
        """规则低 + AI 中 → 中"""
        result = orchestrator._merge_risk_levels("低", [{"risk_level": "中"}])
        assert result == "中"


class TestRunFullReview:
    """run_full_review 完整流程测试"""

    @pytest.mark.asyncio
    async def test_run_full_review_rules_only(self, orchestrator, db_session, monkeypatch):
        """LLM 禁用时应仅返回规则审查结果"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", False)

        _seed_rule(db_session)
        task, _ = _create_task_with_parse(db_session, "ORCH-RULES-ONLY")

        result = await orchestrator.run_full_review(task.id)

        assert result["review_mode"] == "rules_only"
        assert len(result["rule_hits"]) >= 1
        assert result["ai_risk_items"] == []
        assert result["overall_risk_level"] == "高"  # 含高风险规则
        assert "summary_text" in result
        assert "comment_text" in result
        assert "risk_distribution" in result

    @pytest.mark.asyncio
    async def test_run_full_review_with_llm_failure(
        self, orchestrator, db_session, monkeypatch
    ):
        """LLM 启用但调用失败时应降级到纯规则审查"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", True)

        _seed_rule(db_session)
        task, _ = _create_task_with_parse(db_session, "ORCH-LLM-FAIL")

        # Mock _run_llm_review 抛异常
        async def mock_llm_review(*args, **kwargs):
            raise RuntimeError("LLM 不可用")

        monkeypatch.setattr(orchestrator, "_run_llm_review", mock_llm_review)

        result = await orchestrator.run_full_review(task.id)

        # 应降级到纯规则审查
        assert result["review_mode"] == "rules_only"
        assert len(result["rule_hits"]) >= 1
        assert result["ai_risk_items"] == []
        # 不应抛异常
        assert "overall_risk_level" in result

    @pytest.mark.asyncio
    async def test_run_full_review_no_parse_result(
        self, orchestrator, db_session, monkeypatch
    ):
        """无解析结果时应返回低风险空结果"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", False)

        task = ApprovalTask(approval_code="ORCH-NO-PARSE")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        result = await orchestrator.run_full_review(task.id)

        # ReviewService 在无解析结果时返回低风险空结果
        assert result["overall_risk_level"] == "低"
        assert result["rule_hits"] == []

    @pytest.mark.asyncio
    async def test_run_full_review_returns_required_fields(
        self, orchestrator, db_session, monkeypatch
    ):
        """返回结果应包含所有必需字段"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", False)

        _seed_rule(db_session)
        task, _ = _create_task_with_parse(db_session, "ORCH-FIELDS")

        result = await orchestrator.run_full_review(task.id)

        required_fields = [
            "rule_hits",
            "ai_risk_items",
            "overall_risk_level",
            "summary_text",
            "comment_text",
            "focus_points",
            "risk_distribution",
            "ai_assessment",
            "review_mode",
        ]
        for field in required_fields:
            assert field in result, f"返回结果缺少字段: {field}"

    @pytest.mark.asyncio
    async def test_run_full_review_ai_high_risk_added_to_focus_points(
        self, orchestrator, db_session, monkeypatch
    ):
        """AI 高风险项应自动加入审批关注点"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "LLM_ENABLED", True)

        _seed_rule(db_session)
        task, _ = _create_task_with_parse(db_session, "ORCH-AI-FOCUS")

        # Mock _run_llm_review 返回含高风险的 AI 结果
        async def mock_llm_review(*args, **kwargs):
            return {
                "risk_items": [
                    {
                        "risk_type": "AI 高风险",
                        "risk_level": "高",
                        "suggestion": "AI 建议内容",
                    }
                ],
                "ai_summary": "AI 摘要",
                "overall_assessment": "AI 评估",
            }

        monkeypatch.setattr(orchestrator, "_run_llm_review", mock_llm_review)

        result = await orchestrator.run_full_review(task.id)

        assert result["review_mode"] == "rules_and_ai"
        assert len(result["ai_risk_items"]) == 1
        # 应有 AI 高风险关注点
        ai_focus = [p for p in result["focus_points"] if "AI高风险" in p]
        assert len(ai_focus) >= 1
