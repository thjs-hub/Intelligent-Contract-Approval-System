"""M06 规则审查服务单元测试。"""

import pytest

from app.models.attachment import ApprovalAttachment
from app.models.contract_parse import ContractParse
from app.models.review_rule import ReviewRule
from app.models.task import ApprovalTask
from app.services.review_service import ReviewService


def _create_task_with_parse(db_session, code: str = "REVIEW-001") -> tuple[ApprovalTask, ContractParse]:
    """创建带解析结果的任务"""
    task = ApprovalTask(
        approval_code=code,
        approval_title="审查测试任务",
    )
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
            "payment_clause": {"source_text": "预付款50%于签约后支付"},
        },
    )
    db_session.add(parse_record)
    db_session.commit()
    return task, parse_record


def _seed_rules(db_session) -> list[ReviewRule]:
    """创建测试规则"""
    rules = [
        ReviewRule(
            rule_code="R-REVIEW-001",
            rule_name="违约责任规则",
            risk_level="高",
            rule_status="enabled",
            match_mode="keyword",
            match_text="违约金,赔偿",
            suggestion_text="请检查违约责任条款。",
        ),
        ReviewRule(
            rule_code="R-REVIEW-002",
            rule_name="预付款规则",
            risk_level="中",
            rule_status="enabled",
            match_mode="regex",
            match_text=r"预付款.*?(\d{2,3})%",
            suggestion_text="预付款比例过高。",
        ),
    ]
    db_session.add_all(rules)
    db_session.commit()
    return rules


@pytest.mark.asyncio
async def test_run_contract_rules_success(db_session):
    """有解析结果时应成功执行规则审查"""
    _seed_rules(db_session)
    task, _ = _create_task_with_parse(db_session, "REVIEW-SUCC-001")

    service = ReviewService(db_session)
    result = await service.run_contract_rules(task.id)

    assert result["task_id"] == task.id
    assert len(result["hits"]) >= 2  # 应至少命中 2 条规则
    assert result["overall_risk_level"] == "高"  # 含高风险规则
    assert "审查" in result["summary_text"]
    assert len(result["focus_points"]) >= 1  # 高风险关注点


@pytest.mark.asyncio
async def test_run_contract_rules_no_parse_result(db_session):
    """无解析结果时应触发阻塞"""
    _seed_rules(db_session)
    task = ApprovalTask(approval_code="REVIEW-NO-PARSE-001")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    service = ReviewService(db_session)
    result = await service.run_contract_rules(task.id)

    assert result["hits"] == []
    assert result["overall_risk_level"] == "低"

    # 任务应被阻塞
    db_session.refresh(task)
    assert task.task_status == "blocked"


@pytest.mark.asyncio
async def test_run_contract_rules_updates_task_status(db_session):
    """执行审查应将任务状态更新为 reviewing"""
    _seed_rules(db_session)
    task, _ = _create_task_with_parse(db_session, "REVIEW-STATUS-001")

    service = ReviewService(db_session)
    await service.run_contract_rules(task.id)

    db_session.refresh(task)
    assert task.task_status == "reviewing"


def test_calculate_overall_risk_high(db_session):
    """含高风险规则 → 总体风险为高"""
    rules = _seed_rules(db_session)
    task, _ = _create_task_with_parse(db_session, "RISK-HIGH-001")

    # 先创建一些命中记录
    from app.models.rule_hit import RuleHit

    rule_high = next(r for r in rules if r.risk_level == "高")
    rule_medium = next(r for r in rules if r.risk_level == "中")

    hits = [
        RuleHit(task_id=task.id, rule_id=rule_high.id, hit_status="hit"),
        RuleHit(task_id=task.id, rule_id=rule_medium.id, hit_status="hit"),
    ]
    db_session.add_all(hits)
    db_session.commit()

    service = ReviewService(db_session)
    risk = service._calculate_overall_risk(hits)
    assert risk == "高"


def test_calculate_overall_risk_medium_only(db_session):
    """仅含中风险规则 → 总体风险为中"""
    rules = _seed_rules(db_session)
    task, _ = _create_task_with_parse(db_session, "RISK-MED-001")

    from app.models.rule_hit import RuleHit

    rule_medium = next(r for r in rules if r.risk_level == "中")
    hits = [RuleHit(task_id=task.id, rule_id=rule_medium.id, hit_status="hit")]
    db_session.add_all(hits)
    db_session.commit()

    service = ReviewService(db_session)
    risk = service._calculate_overall_risk(hits)
    assert risk == "中"


def test_calculate_overall_risk_no_hits(db_session):
    """无命中 → 总体风险为低"""
    service = ReviewService(db_session)
    risk = service._calculate_overall_risk([])
    assert risk == "低"


def test_generate_summary_with_hits(db_session):
    """有命中时摘要应包含数量和风险等级"""
    _seed_rules(db_session)
    service = ReviewService(db_session)

    from app.models.rule_hit import RuleHit

    summary = service._generate_summary([RuleHit(), RuleHit()], "高", ["关注点1"])
    assert "2" in summary
    assert "高" in summary
    assert "1" in summary  # 1 个高风险关注点


def test_generate_summary_no_hits(db_session):
    """无命中时摘要应说明未发现风险"""
    service = ReviewService(db_session)
    summary = service._generate_summary([], "低", [])
    assert "未发现明显风险" in summary
