"""AI 审查编排 API 集成测试。

测试 /api/v1/orchestrate/ 端点:
  - POST /{task_id}/full-review  执行完整 AI 增强审查
  - GET  /config                 获取 AI 配置开关状态
"""

import pytest
from fastapi.testclient import TestClient

from app.models.contract_parse import ContractParse
from app.models.review_rule import ReviewRule
from app.models.task import ApprovalTask


def _create_full_task(db_session, code: str = "ORCH-API-001"):
    """创建带解析结果和规则的任务"""
    task = ApprovalTask(approval_code=code, approval_title="编排 API 测试")
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

    rule = ReviewRule(
        rule_code=f"R-{code}",
        rule_name="违约责任规则",
        risk_level="高",
        rule_status="enabled",
        match_mode="keyword",
        match_text="违约金",
        suggestion_text="请检查违约责任条款。",
    )
    db_session.add(rule)
    db_session.commit()
    return task


class TestRunFullReview:
    """POST /orchestrate/{task_id}/full-review 测试"""

    def test_full_review_returns_success(self, client: TestClient, db_session):
        """应成功返回完整审查结果"""
        task = _create_full_task(db_session, "ORCH-API-SUCC")

        response = client.post(f"/api/v1/orchestrate/{task.id}/full-review")
        body = response.json()
        assert body["code"] == 0
        assert "overall_risk_level" in body["data"]
        assert "rule_hits" in body["data"]
        assert "ai_risk_items" in body["data"]
        assert "review_mode" in body["data"]
        assert "risk_distribution" in body["data"]
        assert body["data"]["review_mode"] == "rules_only"  # LLM 默认禁用

    def test_full_review_saves_result_to_db(self, client: TestClient, db_session):
        """应将审查结果保存到数据库"""
        from app.models.review_result import ReviewResult

        task = _create_full_task(db_session, "ORCH-API-SAVE")

        client.post(f"/api/v1/orchestrate/{task.id}/full-review")

        # 应已创建 ReviewResult
        result = db_session.query(ReviewResult).filter_by(task_id=task.id).first()
        assert result is not None
        assert result.overall_risk_level == "高"
        assert result.comment_text  # 应有回写评论

    def test_full_review_high_risk_when_keyword_hit(self, client: TestClient, db_session):
        """命中高风险 keyword 规则时应返回高风险"""
        task = _create_full_task(db_session, "ORCH-API-HIGH")

        response = client.post(f"/api/v1/orchestrate/{task.id}/full-review")
        body = response.json()
        assert body["data"]["overall_risk_level"] == "高"
        assert body["data"]["rule_hit_count"] >= 1


class TestGetAIConfig:
    """GET /orchestrate/config 测试"""

    def test_get_config_returns_all_flags(self, client: TestClient):
        """应返回所有 AI 配置开关状态"""
        response = client.get("/api/v1/orchestrate/config")
        body = response.json()
        assert body["code"] == 0

        config = body["data"]
        assert "extractor_type" in config
        assert "nlp_extractor_enabled" in config
        assert "ocr_use_layout" in config
        assert "semantic_enabled" in config
        assert "semantic_threshold" in config
        assert "llm_enabled" in config
        assert "llm_model" in config
        assert "llm_endpoint_configured" in config
        assert "ai_review_enabled" in config
        assert "ai_report_enhance" in config

    def test_get_config_defaults_all_disabled(self, client: TestClient):
        """默认所有 AI 开关应为 False"""
        response = client.get("/api/v1/orchestrate/config")
        config = response.json()["data"]
        # 默认配置
        assert config["llm_enabled"] is False
        assert config["semantic_enabled"] is False
        assert config["ocr_use_layout"] is False
        assert config["ai_review_enabled"] is False
