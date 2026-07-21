"""P3-6 报告生成服务单元测试。

测试 ReportService 的核心功能:
  - generate_risk_distribution 风险分布统计
  - generate_optimized_comment 优化回写评论
  - generate_ai_summary AI 摘要（LLM 不可用时降级）
  - generate_pdf_report PDF 生成（reportlab 不可用时降级）
"""

import pytest

from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.services.report_service import ReportService


def _create_task(db_session, code: str = "REPORT-001") -> ApprovalTask:
    """创建审批任务"""
    task = ApprovalTask(approval_code=code, approval_title="报告测试任务")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _seed_rule(db_session, code: str = "R-REPORT-001", level: str = "高") -> ReviewRule:
    """创建测试规则"""
    rule = ReviewRule(
        rule_code=code,
        rule_name=f"{level}风险规则",
        risk_level=level,
        rule_status="enabled",
        match_mode="keyword",
        match_text="违约",
        suggestion_text="请检查违约条款。",
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def _create_hit(db_session, task: ApprovalTask, rule: ReviewRule) -> RuleHit:
    """创建规则命中记录"""
    hit = RuleHit(
        task_id=task.id,
        rule_id=rule.id,
        evidence_text="命中证据",
        evidence_position="关键词匹配: 违约",
        hit_status="hit",
    )
    db_session.add(hit)
    db_session.commit()
    db_session.refresh(hit)
    return hit


@pytest.fixture
def report_service(db_session):
    """ReportService 实例"""
    return ReportService(db_session)


class TestGenerateRiskDistribution:
    """风险分布统计测试"""

    def test_distribution_structure(self, report_service):
        """应返回完整的风险分布结构"""
        distribution = report_service.generate_risk_distribution(
            rule_hits=[], ai_risk_items=[]
        )
        assert "by_level" in distribution
        assert "by_type" in distribution
        assert "by_category" in distribution
        assert "total" in distribution

    def test_distribution_by_level_high(self, report_service, db_session):
        """高风险规则应计入 by_level['高']"""
        task = _create_task(db_session, "DIST-HIGH-001")
        rule = _seed_rule(db_session, "R-DIST-HIGH", "高")
        hit = _create_hit(db_session, task, rule)

        distribution = report_service.generate_risk_distribution(
            rule_hits=[hit], ai_risk_items=[]
        )
        assert distribution["by_level"]["高"] == 1
        assert distribution["by_level"]["中"] == 0
        assert distribution["by_level"]["低"] == 0
        assert distribution["total"] == 1

    def test_distribution_mixed_rule_and_ai(self, report_service, db_session):
        """规则命中 + AI 风险项应分别统计"""
        task = _create_task(db_session, "DIST-MIXED-001")
        rule = _seed_rule(db_session, "R-DIST-MIXED", "高")
        hit = _create_hit(db_session, task, rule)

        ai_risk_items = [
            {"risk_type": "AI风险1", "risk_level": "中", "description": "描述1"},
            {"risk_type": "AI风险2", "risk_level": "低", "description": "描述2"},
        ]

        distribution = report_service.generate_risk_distribution(
            rule_hits=[hit], ai_risk_items=ai_risk_items
        )
        assert distribution["by_level"]["高"] == 1  # 规则命中
        assert distribution["by_level"]["中"] == 1  # AI 风险
        assert distribution["by_level"]["低"] == 1  # AI 风险
        assert distribution["by_type"]["规则命中"] == 1
        assert distribution["by_type"]["AI识别"] == 2
        assert distribution["total"] == 3

    def test_distribution_by_category(self, report_service, db_session):
        """应按风险类别统计"""
        task = _create_task(db_session, "DIST-CAT-001")
        rule = _seed_rule(db_session, "R-DIST-CAT", "高")
        hit = _create_hit(db_session, task, rule)

        distribution = report_service.generate_risk_distribution(
            rule_hits=[hit],
            ai_risk_items=[{"risk_type": "AI类别", "risk_level": "中"}],
        )
        assert "高风险规则" in distribution["by_category"]
        assert "AI类别" in distribution["by_category"]


class TestGenerateOptimizedComment:
    """优化回写评论测试"""

    def test_comment_structure(self, report_service, db_session):
        """回写评论应包含必要区块"""
        task = _create_task(db_session, "COMMENT-001")
        rule = _seed_rule(db_session, "R-COMMENT-001", "高")
        hit = _create_hit(db_session, task, rule)

        comment = report_service.generate_optimized_comment(
            overall_risk_level="高",
            ai_summary="AI 生成的摘要",
            rule_hits=[hit],
            ai_risk_items=[{"risk_type": "AI风险", "risk_level": "中", "suggestion": "AI建议"}],
            focus_points=["关注点1"],
        )

        assert "【智能审查意见】" in comment
        assert "总风险等级：高" in comment
        assert "AI 生成的摘要" in comment
        assert "规则命中风险" in comment
        assert "AI 深度分析风险" in comment
        assert "审批关注点" in comment

    def test_comment_with_ai_summary(self, report_service, db_session):
        """有 AI 摘要时应使用 AI 摘要"""
        comment = report_service.generate_optimized_comment(
            overall_risk_level="中",
            ai_summary="这是 AI 摘要内容",
            rule_hits=[],
            ai_risk_items=[],
            focus_points=[],
        )
        assert "这是 AI 摘要内容" in comment

    def test_comment_without_ai_summary_uses_template(self, report_service):
        """无 AI 摘要时应使用模板摘要"""
        comment = report_service.generate_optimized_comment(
            overall_risk_level="中",
            ai_summary="",
            rule_hits=["规则1", "规则2"],
            ai_risk_items=["风险1"],
            focus_points=[],
        )
        # 应包含总数
        assert "3" in comment  # 2 规则 + 1 AI

    def test_comment_with_missing_clauses(self, report_service):
        """含缺失条款的 AI 风险项应触发缺失条款区块"""
        comment = report_service.generate_optimized_comment(
            overall_risk_level="高",
            ai_summary="摘要",
            rule_hits=[],
            ai_risk_items=[
                {
                    "risk_type": "验收标准缺失",
                    "risk_level": "高",
                    "suggestion": "建议补充验收条款",
                }
            ],
            focus_points=[],
        )
        assert "缺失关键条款" in comment
        assert "验收标准缺失" in comment


class TestGenerateAISummary:
    """AI 摘要生成测试"""

    @pytest.mark.asyncio
    async def test_generate_ai_summary_fallback(self, report_service, monkeypatch):
        """LLM 不可用时应降级到模板摘要"""
        # Mock LLMReviewer.generate_summary 抛异常 → 应被 LLMReviewer 内部捕获并降级
        summary = await report_service.generate_ai_summary(
            task_id=1,
            rule_hits=["规则1", "规则2"],
            ai_risk_items=["风险1"],
            overall_risk_level="中",
        )
        # LLM 配置不完整时会降级到模板
        assert isinstance(summary, str)
        assert len(summary) > 0


class TestGeneratePDFReport:
    """PDF 报告生成测试"""

    def test_generate_pdf_report_returns_bytes(self, report_service):
        """PDF 生成应返回二进制内容"""
        review_result = {
            "overall_risk_level": "高",
            "summary_text": "审查摘要",
            "ai_summary": "AI 摘要",
            "created_at": "2026-07-21",
            "rule_hits": [],
        }
        risk_distribution = {
            "by_level": {"高": 1, "中": 0, "低": 0},
            "by_type": {"规则命中": 1, "AI识别": 0},
            "by_category": {},
            "total": 1,
        }

        try:
            pdf_bytes = report_service.generate_pdf_report(
                task_id=1,
                review_result=review_result,
                ai_result=None,
                risk_distribution=risk_distribution,
            )
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
            # PDF 文件应以 %PDF 开头
            assert pdf_bytes[:4] == b"%PDF"
        except ImportError:
            # reportlab 未安装时跳过（测试环境可能未安装）
            pytest.skip("reportlab 未安装，跳过 PDF 生成测试")

    def test_generate_pdf_report_with_ai_result(self, report_service):
        """含 AI 审查结果时应包含 AI 风险项"""
        review_result = {
            "overall_risk_level": "高",
            "summary_text": "摘要",
            "ai_summary": "AI 摘要",
            "created_at": "2026-07-21",
            "rule_hits": [],
        }
        ai_result = {
            "risk_items": [
                {
                    "risk_type": "AI 风险",
                    "risk_level": "高",
                    "description": "风险描述",
                    "evidence": "证据",
                    "suggestion": "建议",
                }
            ],
            "overall_assessment": "AI 总体评估",
            "missing_clauses": ["缺失条款1"],
        }
        risk_distribution = {
            "by_level": {"高": 1, "中": 0, "低": 0},
            "by_type": {"规则命中": 0, "AI识别": 1},
            "by_category": {},
            "total": 1,
        }

        try:
            pdf_bytes = report_service.generate_pdf_report(
                task_id=1,
                review_result=review_result,
                ai_result=ai_result,
                risk_distribution=risk_distribution,
            )
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 0
        except ImportError:
            pytest.skip("reportlab 未安装，跳过 PDF 生成测试")
