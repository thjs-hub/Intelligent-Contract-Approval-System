"""P3-5 规则评测服务单元测试。

测试 RuleEvaluator 的核心功能:
  - evaluate_all 评测所有规则
  - get_rule_detail 获取单条规则详情
  - get_evaluation_summary 获取评测汇总
  - 状态判定（never_hit / too_broad / low_hit / active）
"""


from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.services.rule_evaluator import RuleEvaluator


def _create_tasks(db_session, count: int = 5, status: str = "done") -> list[ApprovalTask]:
    """创建多个审批任务（默认已审查完成状态）"""
    tasks = []
    for i in range(count):
        task = ApprovalTask(
            approval_code=f"EVAL-TASK-{i:03d}",
            task_status=status,
        )
        db_session.add(task)
        tasks.append(task)
    db_session.commit()
    for t in tasks:
        db_session.refresh(t)
    return tasks


def _seed_rules(db_session) -> list[ReviewRule]:
    """创建测试规则（覆盖三种匹配模式）"""
    rules = [
        ReviewRule(
            rule_code="R-EVAL-001",
            rule_name="高频命中规则",
            risk_level="高",
            rule_status="enabled",
            match_mode="keyword",
            match_text="违约",
            suggestion_text="建议1",
        ),
        ReviewRule(
            rule_code="R-EVAL-002",
            rule_name="从未命中规则",
            risk_level="中",
            rule_status="enabled",
            match_mode="keyword",
            match_text="不存在的关键词XYZ",
            suggestion_text="建议2",
        ),
        ReviewRule(
            rule_code="R-EVAL-003",
            rule_name="低频命中规则",
            risk_level="低",
            rule_status="enabled",
            match_mode="regex",
            match_text=r"罕见模式ABC\d+",
            suggestion_text="建议3",
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    for r in rules:
        db_session.refresh(r)
    return rules


def _create_hits(db_session, rule: ReviewRule, task: ApprovalTask, count: int = 1):
    """为指定规则创建命中记录"""
    for _ in range(count):
        hit = RuleHit(
            task_id=task.id,
            rule_id=rule.id,
            evidence_text="命中证据文本",
            evidence_position="关键词匹配: 违约",
            hit_status="hit",
        )
        db_session.add(hit)
    db_session.commit()


class TestRuleEvaluatorEvaluateAll:
    """evaluate_all 测试"""

    def test_evaluate_all_returns_all_rules(self, db_session):
        """应返回所有规则的评测数据"""
        _seed_rules(db_session)
        evaluator = RuleEvaluator(db_session)
        results = evaluator.evaluate_all()

        assert len(results) == 3
        rule_codes = [r["rule_code"] for r in results]
        assert "R-EVAL-001" in rule_codes
        assert "R-EVAL-002" in rule_codes
        assert "R-EVAL-003" in rule_codes

    def test_evaluate_all_never_hit_status(self, db_session):
        """从未命中的规则状态应为 never_hit"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 5)

        # 仅为 R-EVAL-001 创建命中
        _create_hits(db_session, rules[0], tasks[0], count=1)

        evaluator = RuleEvaluator(db_session)
        results = evaluator.evaluate_all()

        never_hit_rule = next(r for r in results if r["rule_code"] == "R-EVAL-002")
        assert never_hit_rule["status"] == "never_hit"
        assert never_hit_rule["hit_count"] == 0
        assert never_hit_rule["hit_rate"] == 0.0

    def test_evaluate_all_too_broad_status(self, db_session):
        """命中率 > 0.8 的规则状态应为 too_broad"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 5)

        # 为 R-EVAL-001 在所有 5 个任务中创建命中（命中率 = 1.0）
        for task in tasks:
            _create_hits(db_session, rules[0], task, count=1)

        evaluator = RuleEvaluator(db_session)
        results = evaluator.evaluate_all()

        too_broad_rule = next(r for r in results if r["rule_code"] == "R-EVAL-001")
        assert too_broad_rule["status"] == "too_broad"
        assert too_broad_rule["hit_count"] == 5
        assert too_broad_rule["hit_rate"] == 1.0

    def test_evaluate_all_active_status(self, db_session):
        """命中率在合理范围（0.05~0.8）的规则状态应为 active"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 10)

        # 为 R-EVAL-001 在 3 个任务中创建命中（命中率 = 0.3）
        for task in tasks[:3]:
            _create_hits(db_session, rules[0], task, count=1)

        evaluator = RuleEvaluator(db_session)
        results = evaluator.evaluate_all()

        active_rule = next(r for r in results if r["rule_code"] == "R-EVAL-001")
        assert active_rule["status"] == "active"
        assert active_rule["hit_count"] == 3

    def test_evaluate_all_no_hits_returns_empty_stats(self, db_session):
        """无任何命中记录时返回正常结构"""
        _seed_rules(db_session)
        # 创建一些已审查任务（无命中）
        _create_tasks(db_session, 3, status="done")
        evaluator = RuleEvaluator(db_session)
        results = evaluator.evaluate_all()

        assert len(results) == 3
        for r in results:
            assert r["hit_count"] == 0
            assert r["hit_rate"] == 0.0
            assert r["status"] == "never_hit"


class TestRuleEvaluatorGetRuleDetail:
    """get_rule_detail 测试"""

    def test_get_rule_detail_returns_rule_info(self, db_session):
        """应返回规则详情"""
        rules = _seed_rules(db_session)
        evaluator = RuleEvaluator(db_session)
        detail = evaluator.get_rule_detail(rules[0].id)

        assert detail["rule"]["rule_code"] == "R-EVAL-001"
        assert detail["rule"]["rule_name"] == "高频命中规则"
        assert "recent_hits" in detail

    def test_get_rule_detail_includes_recent_hits(self, db_session):
        """应包含最近命中记录"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 3)
        _create_hits(db_session, rules[0], tasks[0], count=2)

        evaluator = RuleEvaluator(db_session)
        detail = evaluator.get_rule_detail(rules[0].id)

        assert len(detail["recent_hits"]) == 2
        for hit in detail["recent_hits"]:
            assert "task_id" in hit
            assert "evidence_text" in hit
            assert "evidence_position" in hit
            assert "created_at" in hit

    def test_get_rule_detail_nonexistent_returns_empty(self, db_session):
        """不存在的规则 ID 应返回空字典"""
        evaluator = RuleEvaluator(db_session)
        detail = evaluator.get_rule_detail(99999)
        assert detail == {}

    def test_get_rule_detail_limits_to_20_hits(self, db_session):
        """最近命中记录应限制为 20 条"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 25)
        for task in tasks:
            _create_hits(db_session, rules[0], task, count=1)

        evaluator = RuleEvaluator(db_session)
        detail = evaluator.get_rule_detail(rules[0].id)

        assert len(detail["recent_hits"]) <= 20


class TestRuleEvaluatorGetSummary:
    """get_evaluation_summary 测试"""

    def test_summary_structure(self, db_session):
        """汇总数据应包含所有字段"""
        _seed_rules(db_session)
        evaluator = RuleEvaluator(db_session)
        summary = evaluator.get_evaluation_summary()

        assert "total_rules" in summary
        assert "active_rules" in summary
        assert "never_hit_rules" in summary
        assert "too_broad_rules" in summary
        assert "low_hit_rules" in summary
        assert "total_tasks" in summary
        assert "total_hits" in summary
        assert "avg_hit_rate" in summary

    def test_summary_counts_correct(self, db_session):
        """汇总计数应正确"""
        rules = _seed_rules(db_session)
        tasks = _create_tasks(db_session, 10)

        # R-EVAL-001 在 3 个任务命中（active）
        for task in tasks[:3]:
            _create_hits(db_session, rules[0], task, count=1)
        # R-EVAL-002 从未命中（never_hit）
        # R-EVAL-003 从未命中（never_hit）

        evaluator = RuleEvaluator(db_session)
        summary = evaluator.get_evaluation_summary()

        assert summary["total_rules"] == 3
        assert summary["active_rules"] == 1
        assert summary["never_hit_rules"] == 2
        assert summary["total_hits"] == 3
