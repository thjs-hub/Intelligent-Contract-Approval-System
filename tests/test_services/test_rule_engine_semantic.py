"""P3-2 RuleMatcher 语义匹配分支集成测试 + 第二阶段回归测试。

验证:
  1. semantic 分支在 SEMANTIC_ENABLED=False 时跳过（不影响其他规则）
  2. semantic 分支在依赖未安装时跳过并记录警告（不影响其他规则）
  3. keyword/regex 规则在新增 semantic 分支后仍正常工作（回归）
  4. 含 semantic 规则的审查流程端到端可走通
"""

import pytest

from app.models.contract_parse import ContractParse
from app.models.review_rule import ReviewRule
from app.models.task import ApprovalTask
from app.services.rule_engine import RuleMatcher


def _create_task_with_parse(db_session, code: str = "SEMANTIC-001"):
    """创建带解析结果的任务"""
    task = ApprovalTask(approval_code=code, approval_title="语义匹配测试任务")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    parse_record = ContractParse(
        task_id=task.id,
        parse_status="success",
        basic_info_json={
            "contract_amount": {"source_text": "合同金额：人民币100万元"},
        },
        clause_info_json={
            "breach_clause": {"source_text": "甲方有权单方面变更合同内容"},
            "payment_clause": {"source_text": "预付款50%于签约后支付"},
        },
    )
    db_session.add(parse_record)
    db_session.commit()
    return task, parse_record


def _seed_mixed_rules(db_session) -> list[ReviewRule]:
    """创建含三种匹配模式的规则"""
    rules = [
        ReviewRule(
            rule_code="R-KEYWORD-001",
            rule_name="违约责任规则",
            risk_level="高",
            rule_status="enabled",
            match_mode="keyword",
            match_text="违约金,赔偿",
            suggestion_text="请检查违约责任条款。",
        ),
        ReviewRule(
            rule_code="R-REGEX-001",
            rule_name="预付款规则",
            risk_level="中",
            rule_status="enabled",
            match_mode="regex",
            match_text=r"预付款.*?(\d{2,3})%",
            suggestion_text="预付款比例过高。",
        ),
        ReviewRule(
            rule_code="R-SEMANTIC-001",
            rule_name="不平等条款检测",
            risk_level="高",
            rule_status="enabled",
            match_mode="semantic",
            match_text="甲方有权单方面变更合同内容,甲方有权随时终止合同",
            suggestion_text="合同中存在甲方单方面权利条款。",
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


class TestRuleMatcherSemanticBranch:
    """semantic 分支行为测试"""

    def test_semantic_skipped_when_disabled(self, db_session, monkeypatch):
        """SEMANTIC_ENABLED=False 时 semantic 规则应被跳过"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", False)

        _seed_mixed_rules(db_session)
        task, _ = _create_task_with_parse(db_session, "SEMANTIC-DISABLED")

        matcher = RuleMatcher(db_session)
        # 直接调用 _match_rule 测试 semantic 分支
        semantic_rule = db_session.query(ReviewRule).filter_by(
            rule_code="R-SEMANTIC-001"
        ).first()
        search_text = "甲方有权单方面变更合同内容"

        evidence, position = matcher._match_rule(semantic_rule, search_text)
        # 应返回 None（被跳过）
        assert evidence is None
        assert position is None

    def test_semantic_skipped_when_dependency_missing(self, db_session, monkeypatch):
        """sentence-transformers 未安装时 semantic 规则应被跳过"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", True)

        _seed_mixed_rules(db_session)
        task, _ = _create_task_with_parse(db_session, "SEMANTIC-NO-DEP")

        matcher = RuleMatcher(db_session)
        semantic_rule = db_session.query(ReviewRule).filter_by(
            rule_code="R-SEMANTIC-001"
        ).first()
        search_text = "甲方有权单方面变更合同内容"

        # 依赖未安装时跳过，返回 None
        evidence, position = matcher._match_rule(semantic_rule, search_text)
        assert evidence is None
        assert position is None

    def test_semantic_skipped_when_empty_search_text(self, db_session, monkeypatch):
        """search_text 为空时 semantic 规则应被跳过"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", True)

        _seed_mixed_rules(db_session)
        matcher = RuleMatcher(db_session)
        semantic_rule = db_session.query(ReviewRule).filter_by(
            rule_code="R-SEMANTIC-001"
        ).first()

        evidence, position = matcher._match_rule(semantic_rule, "")
        assert evidence is None
        assert position is None


class TestRuleMatcherRegression:
    """第二阶段 keyword/regex 规则回归测试"""

    def test_keyword_rules_still_work_with_semantic_branch(self, db_session, monkeypatch):
        """新增 semantic 分支后 keyword 规则仍正常工作"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", False)

        _seed_mixed_rules(db_session)
        task, _ = _create_task_with_parse(db_session, "REGRESSION-KEYWORD")

        matcher = RuleMatcher(db_session)
        hits, focus_points = matcher.match_all(
            task_id=task.id,
            basic_info={
                "contract_amount": {"source_text": "合同金额：违约金100万"},
            },
            clause_info={
                "breach_clause": {"source_text": "违约金按合同金额10%收取"},
                "payment_clause": {"source_text": "预付款50%于签约后支付"},
            },
        )

        # 应命中 keyword 规则（违约金）
        keyword_hits = [h for h in hits if "违约" in (
            db_session.query(ReviewRule).get(h.rule_id).rule_name or ""
        )]
        assert len(keyword_hits) >= 1

    def test_regex_rules_still_work_with_semantic_branch(self, db_session, monkeypatch):
        """新增 semantic 分支后 regex 规则仍正常工作"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", False)

        _seed_mixed_rules(db_session)
        task, _ = _create_task_with_parse(db_session, "REGRESSION-REGEX")

        matcher = RuleMatcher(db_session)
        hits, focus_points = matcher.match_all(
            task_id=task.id,
            basic_info={},
            clause_info={
                "payment_clause": {"source_text": "预付款50%于签约后支付"},
            },
        )

        # 应命中 regex 规则（预付款）
        regex_hits = [h for h in hits if "预付款" in (
            db_session.query(ReviewRule).get(h.rule_id).rule_name or ""
        )]
        assert len(regex_hits) >= 1

    def test_mixed_rules_match_all_works(self, db_session, monkeypatch):
        """三种模式混合时 match_all 应正常工作"""
        from app.core.config import settings

        # 启用 semantic 但依赖未安装（应被跳过）
        monkeypatch.setattr(settings, "SEMANTIC_ENABLED", True)

        _seed_mixed_rules(db_session)
        task, _ = _create_task_with_parse(db_session, "REGRESSION-MIXED")

        matcher = RuleMatcher(db_session)
        hits, focus_points = matcher.match_all(
            task_id=task.id,
            basic_info={
                "contract_amount": {"source_text": "合同金额：100万"},
            },
            clause_info={
                "breach_clause": {"source_text": "违约金按合同金额10%收取"},
                "payment_clause": {"source_text": "预付款50%于签约后支付"},
            },
        )

        # 应命中 keyword + regex 规则（semantic 因依赖未安装被跳过）
        assert len(hits) >= 2

        # 高风险规则应进入 focus_points
        assert len(focus_points) >= 1
