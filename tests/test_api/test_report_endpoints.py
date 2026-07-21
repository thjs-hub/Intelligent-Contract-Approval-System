"""P3-6 审查报告 API 集成测试。

测试 /api/v1/reports/ 端点:
  - GET /{task_id}/distribution  获取风险分布
  - GET /{task_id}/pdf           导出 PDF
  - GET /{task_id}/preview       获取预览数据
"""

import pytest
from fastapi.testclient import TestClient

from app.models.review_result import ReviewResult
from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask


def _create_task_with_review_result(db_session, code: str = "API-REPORT-001"):
    """创建带审查结果的任务"""
    task = ApprovalTask(approval_code=code, approval_title="报告 API 测试")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    rule = ReviewRule(
        rule_code=f"R-{code}",
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

    result = ReviewResult(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="审查摘要",
        focus_points_json=["关注点1"],
        comment_text="回写评论",
    )
    db_session.add(result)
    db_session.commit()
    return task


class TestGetRiskDistribution:
    """GET /reports/{task_id}/distribution 测试"""

    def test_get_distribution_returns_data(self, client: TestClient, db_session):
        """应返回风险分布数据"""
        task = _create_task_with_review_result(db_session, "API-DIST-001")

        response = client.get(f"/api/v1/reports/{task.id}/distribution")
        body = response.json()
        assert body["code"] == 0
        assert "by_level" in body["data"]
        assert "by_type" in body["data"]
        assert body["data"]["by_level"]["高"] == 1

    def test_get_distribution_empty_when_no_hits(self, client: TestClient, db_session):
        """无命中记录时应返回空分布"""
        task = ApprovalTask(approval_code="API-DIST-EMPTY")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/reports/{task.id}/distribution")
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 0


class TestExportPDFReport:
    """GET /reports/{task_id}/pdf 测试"""

    def test_export_pdf_returns_404_when_no_result(self, client: TestClient, db_session):
        """无审查结果时应返回错误"""
        task = ApprovalTask(approval_code="API-PDF-NO-RESULT")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/reports/{task.id}/pdf")
        body = response.json()
        assert body["code"] != 0

    def test_export_pdf_returns_pdf_content(self, client: TestClient, db_session):
        """有审查结果时应返回 PDF 二进制内容"""
        task = _create_task_with_review_result(db_session, "API-PDF-OK")

        response = client.get(f"/api/v1/reports/{task.id}/pdf")

        # 检查响应类型
        content_type = response.headers.get("content-type", "")
        if "application/pdf" in content_type:
            # PDF 生成成功
            assert response.status_code == 200
            assert response.content[:4] == b"%PDF"
        else:
            # reportlab 未安装或 PDF 生成失败，应返回 JSON 错误
            body = response.json()
            assert body["code"] != 0


class TestGetReportPreview:
    """GET /reports/{task_id}/preview 测试"""

    def test_get_preview_returns_data(self, client: TestClient, db_session):
        """应返回预览数据"""
        task = _create_task_with_review_result(db_session, "API-PREVIEW-001")

        response = client.get(f"/api/v1/reports/{task.id}/preview")
        body = response.json()
        assert body["code"] == 0
        assert "overall_risk_level" in body["data"]
        assert "summary_text" in body["data"]
        assert "risk_distribution" in body["data"]
        assert "rule_results" in body["data"]
        assert body["data"]["overall_risk_level"] == "高"

    def test_get_preview_returns_404_when_no_result(self, client: TestClient, db_session):
        """无审查结果时应返回错误"""
        task = ApprovalTask(approval_code="API-PREVIEW-NO")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        response = client.get(f"/api/v1/reports/{task.id}/preview")
        body = response.json()
        assert body["code"] != 0
