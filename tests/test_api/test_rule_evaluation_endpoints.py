"""P3-5 规则评测 API 集成测试。

测试 /api/v1/rule-evaluation/ 端点:
  - GET /                  获取所有规则评测数据
  - GET /summary           获取评测汇总
  - GET /{rule_id}         获取单条规则详细评测
"""

import pytest
from fastapi.testclient import TestClient

from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask


def _seed_rules_and_hits(db_session):
    """创建规则和命中记录"""
    task = ApprovalTask(approval_code="EVAL-API-TASK")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    rule = ReviewRule(
        rule_code="R-EVAL-API-001",
        rule_name="违约责任规则",
        risk_level="高",
        rule_status="enabled",
        match_mode="keyword",
        match_text="违约",
        suggestion_text="请检查违约条款。",
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    hit = RuleHit(
        task_id=task.id,
        rule_id=rule.id,
        evidence_text="命中证据",
        evidence_position="关键词匹配",
        hit_status="hit",
    )
    db_session.add(hit)
    db_session.commit()
    return rule, task


class TestGetRuleEvaluation:
    """GET /rule-evaluation/ 测试"""

    def test_get_evaluation_returns_list(self, client: TestClient, db_session):
        """应返回规则评测列表"""
        _seed_rules_and_hits(db_session)

        response = client.get("/api/v1/rule-evaluation/")
        body = response.json()
        assert body["code"] == 0
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1

    def test_get_evaluation_includes_required_fields(self, client: TestClient, db_session):
        """评测数据应包含必需字段"""
        _seed_rules_and_hits(db_session)

        response = client.get("/api/v1/rule-evaluation/")
        body = response.json()
        first = body["data"][0]
        assert "rule_id" in first
        assert "rule_code" in first
        assert "rule_name" in first
        assert "match_mode" in first
        assert "risk_level" in first
        assert "hit_count" in first
        assert "hit_rate" in first
        assert "status" in first


class TestGetEvaluationSummary:
    """GET /rule-evaluation/summary 测试"""

    def test_get_summary_returns_data(self, client: TestClient, db_session):
        """应返回汇总数据"""
        _seed_rules_and_hits(db_session)

        response = client.get("/api/v1/rule-evaluation/summary")
        body = response.json()
        assert body["code"] == 0
        assert "total_rules" in body["data"]
        assert "active_rules" in body["data"]
        assert "never_hit_rules" in body["data"]
        assert "total_hits" in body["data"]


class TestGetRuleDetailEvaluation:
    """GET /rule-evaluation/{rule_id} 测试"""

    def test_get_detail_returns_data(self, client: TestClient, db_session):
        """应返回规则详细评测"""
        rule, _ = _seed_rules_and_hits(db_session)

        response = client.get(f"/api/v1/rule-evaluation/{rule.id}")
        body = response.json()
        assert body["code"] == 0
        assert "rule" in body["data"]
        assert "recent_hits" in body["data"]
        assert body["data"]["rule"]["rule_code"] == "R-EVAL-API-001"

    def test_get_detail_returns_404_when_not_exist(self, client: TestClient):
        """不存在的规则 ID 应返回错误"""
        response = client.get("/api/v1/rule-evaluation/99999")
        body = response.json()
        assert body["code"] != 0
