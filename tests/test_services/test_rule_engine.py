"""M06 规则匹配引擎单元测试。"""

import pytest

from app.models.review_rule import ReviewRule
from app.services.rule_engine import RuleMatcher


def _seed_rules(db_session) -> list[ReviewRule]:
    """创建测试用规则"""
    rules = [
        ReviewRule(
            rule_code="TEST-KW-001",
            rule_name="测试关键词规则",
            risk_level="高",
            rule_status="enabled",
            match_mode="keyword",
            match_text="违约金,赔偿,罚则",
            suggestion_text="请检查违约责任条款。",
        ),
        ReviewRule(
            rule_code="TEST-REGEX-001",
            rule_name="测试正则规则",
            risk_level="中",
            rule_status="enabled",
            match_mode="regex",
            match_text=r"预付款.*?(\d{2,3})%",
            suggestion_text="预付款比例过高。",
        ),
        ReviewRule(
            rule_code="TEST-DISABLED-001",
            rule_name="已禁用规则",
            risk_level="高",
            rule_status="disabled",
            match_mode="keyword",
            match_text="违约金",
            suggestion_text="不应被执行。",
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


class TestRuleMatcherKeyword:
    """关键词匹配测试"""

    def test_keyword_match_hit(self, db_session):
        """包含关键词的文本应命中"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        text = "任一方违约应支付合同金额10%的违约金"
        result = matcher._keyword_match(["违约金", "赔偿"], text)
        evidence, position = result

        assert evidence is not None
        assert "违约金" in evidence
        assert "关键词匹配" in position

    def test_keyword_match_miss(self, db_session):
        """不包含关键词的文本不应命中"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        text = "本合同不涉及违约责任"
        result = matcher._keyword_match(["违约金", "罚则"], text)
        assert result == (None, None)

    def test_keyword_match_returns_context(self, db_session):
        """关键词匹配应返回上下文证据"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        # 构造长文本，关键词在中间
        text = "前" * 100 + "违约金" + "后" * 100
        evidence, _ = matcher._keyword_match(["违约金"], text)

        # 证据应包含关键词及其前后 50 字符
        assert "违约金" in evidence
        assert len(evidence) <= 50 + len("违约金") + 50 + 1


class TestRuleMatcherRegex:
    """正则匹配测试"""

    def test_regex_match_hit(self, db_session):
        """匹配正则的文本应命中"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        text = "合同签订后7日内支付预付款50%"
        evidence, position = matcher._regex_match([r"预付款.*?(\d{2,3})%"], text)

        assert evidence is not None
        assert "预付款" in evidence
        assert "正则匹配" in position

    def test_regex_match_miss(self, db_session):
        """不匹配正则的文本不应命中"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        text = "本合同无预付款条款"
        result = matcher._regex_match([r"预付款.*?(\d{2,3})%"], text)
        assert result == (None, None)

    def test_regex_invalid_pattern_skipped(self, db_session):
        """无效正则应被跳过，不抛异常"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        text = "测试文本"
        # 第一个 pattern 无效，第二个有效但不匹配
        result = matcher._regex_match([r"[invalid", r"有效正则"], text)
        assert result == (None, None)


class TestRuleMatcherMatchAll:
    """match_all 集成测试"""

    def test_match_all_returns_hits(self, db_session):
        """应返回所有启用规则的命中结果"""
        rules = _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        basic_info = {
            "contract_amount": {"source_text": "合同金额：100万"},
        }
        clause_info = {
            "breach_clause": {"source_text": "违约金按合同金额10%收取"},
            "payment_clause": {"source_text": "预付款50%于签约后支付"},
        }

        # 先创建一个任务
        from app.models.task import ApprovalTask

        task = ApprovalTask(approval_code="RULE-001")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        hits, focus_points = matcher.match_all(task.id, basic_info, clause_info)

        # 应至少命中 2 条（关键词规则 + 正则规则）
        assert len(hits) >= 2
        # 高风险规则的命中应进入关注点
        assert len(focus_points) >= 1
        assert any("高风险" in fp for fp in focus_points)

    def test_match_all_skips_disabled_rules(self, db_session):
        """已禁用规则不应被执行"""
        rules = _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        from app.models.task import ApprovalTask

        task = ApprovalTask(approval_code="RULE-002")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        # 文本包含禁用规则的关键词
        basic_info = {"x": {"source_text": "违约金"}}
        clause_info = {}

        hits, _ = matcher.match_all(task.id, basic_info, clause_info)

        # 应只命中启用规则（TEST-KW-001），不命中禁用规则
        hit_rule_ids = [h.rule_id for h in hits]
        disabled_rule = next(r for r in rules if r.rule_code == "TEST-DISABLED-001")
        assert disabled_rule.id not in hit_rule_ids

    def test_match_all_empty_text(self, db_session):
        """空文本不应命中任何规则"""
        _seed_rules(db_session)
        matcher = RuleMatcher(db_session)

        from app.models.task import ApprovalTask

        task = ApprovalTask(approval_code="RULE-003")
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        hits, focus_points = matcher.match_all(task.id, {}, {})
        assert hits == []
        assert focus_points == []


class TestBuildSearchText:
    """_build_search_text 测试"""

    def test_build_search_text_concatenates_sources(self, db_session):
        """应拼接所有 source_text"""
        matcher = RuleMatcher(db_session)
        basic_info = {
            "field1": {"source_text": "基本信息文本"},
            "field2": {"source_text": "另一段基本信息"},
        }
        clause_info = {
            "clause1": {"source_text": "条款文本"},
            "clause2": {"extracted": False},  # 无 source_text
        }

        text = matcher._build_search_text(basic_info, clause_info)
        assert "基本信息文本" in text
        assert "另一段基本信息" in text
        assert "条款文本" in text

    def test_build_search_text_empty(self, db_session):
        """空字典应返回空字符串"""
        matcher = RuleMatcher(db_session)
        assert matcher._build_search_text({}, {}) == ""
