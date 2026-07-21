"""P3-4 AI 智能审查 API 集成测试。

测试 /api/v1/ai-review/ 端点:
  - POST /trigger/{task_id}  触发 AI 审查
  - GET  /results/{task_id}  获取 AI 审查结果
"""

import pytest
from fastapi.testclient import TestClient

from app.models.contract_parse import ContractParse
from app.models.task import ApprovalTask


def _create_task_with_parse(db_session, code: str = "API-AI-001"):
    """创建带解析结果的任务"""
    task = ApprovalTask(approval_code=code, approval_title="AI API 测试任务")
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
            "breach_clause": {"source_text": "违约金条款"},
        },
    )
    db_session.add(parse_record)
    db_session.commit()
    return task


class TestTriggerAIReview:
    """POST /ai-review/trigger/{task_id} 测试"""

    def test_trigger_returns_400_when_llm_disabled(self, client: TestClient, db_session):
        """LLM 未启用时应返回 400"""
        task = _create_task_with_parse(db_session, "API-AI-DISABLED")
        response = client.post(f"/api/v1/ai-review/trigger/{task.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["code"] != 0
        assert "未启用" in body["message"]

    def test_trigger_returns_400_when_no_parse_result(self, client: TestClient, db_session):
        """无解析结果时应返回 400"""
        from app.core.config import settings

        # 临时启用 LLM 但不配置 endpoint
        original = settings.LLM_ENABLED
        settings.LLM_ENABLED = True
        try:
            task = ApprovalTask(approval_code="API-AI-NO-PARSE")
            db_session.add(task)
            db_session.commit()
            db_session.refresh(task)

            response = client.post(f"/api/v1/ai-review/trigger/{task.id}")
            body = response.json()
            # 应返回错误（无解析结果）
            assert body["code"] != 0
        finally:
            settings.LLM_ENABLED = original


class TestGetAIReviewResult:
    """GET /ai-review/results/{task_id} 测试"""

    def test_get_result_returns_404_when_not_exist(self, client: TestClient, db_session):
        """无 AI 审查结果时应返回 404"""
        task = ApprovalTask(approval_code="API-AI-NO-RESULT")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/ai-review/results/{task.id}")
        body = response.json()
        assert body["code"] != 0

    def test_get_result_returns_data_when_exist(self, client: TestClient, db_session):
        """有 AI 审查结果时应返回数据"""
        from app.models.ai_review_result import AIReviewResult

        task = ApprovalTask(approval_code="API-AI-HAS-RESULT")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        ai_result = AIReviewResult(
            task_id=task.id,
            risk_items_json=[{"risk_type": "测试风险", "risk_level": "中"}],
            overall_assessment="测试评估",
            missing_clauses_json=["缺失条款"],
            ai_summary="测试摘要",
            model_name="test-model",
        )
        db_session.add(ai_result)
        db_session.commit()

        response = client.get(f"/api/v1/ai-review/results/{task.id}")
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["risk_items"][0]["risk_type"] == "测试风险"
        assert body["data"]["ai_summary"] == "测试摘要"
        assert body["data"]["model_name"] == "test-model"
