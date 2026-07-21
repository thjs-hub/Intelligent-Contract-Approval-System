"""M07 审查结果管理服务单元测试。"""


from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.services.result_service import ResultService


def _create_task(db_session, code: str = "RESULT-001") -> ApprovalTask:
    task = ApprovalTask(
        approval_code=code,
        approval_title="结果测试任务",
        task_status="reviewing",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _create_rules_and_hits(db_session, task: ApprovalTask) -> list[RuleHit]:
    """创建规则和命中记录"""
    rule1 = ReviewRule(
        rule_code="RES-R001",
        rule_name="高风险规则",
        risk_level="高",
        rule_status="enabled",
        match_mode="keyword",
        match_text="违约金",
        suggestion_text="请检查违约责任。",
    )
    rule2 = ReviewRule(
        rule_code="RES-R002",
        rule_name="中风险规则",
        risk_level="中",
        rule_status="enabled",
        match_mode="keyword",
        match_text="预付款",
        suggestion_text="预付款过高。",
    )
    db_session.add_all([rule1, rule2])
    db_session.commit()
    db_session.refresh(rule1)
    db_session.refresh(rule2)

    hits = [
        RuleHit(task_id=task.id, rule_id=rule1.id, evidence_text="违约金10%", hit_status="hit"),
        RuleHit(task_id=task.id, rule_id=rule2.id, evidence_text="预付款50%", hit_status="hit"),
    ]
    db_session.add_all(hits)
    db_session.commit()
    return hits


def test_save_review_result_creates_new(db_session):
    """首次保存应创建新记录"""
    task = _create_task(db_session, "SAVE-NEW-001")
    hits = _create_rules_and_hits(db_session, task)

    service = ResultService(db_session)
    result = service.save_review_result(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="测试摘要",
        focus_points=["关注点1"],
        hits=hits,
    )

    assert result.id is not None
    assert result.task_id == task.id
    assert result.overall_risk_level == "高"
    assert result.summary_text == "测试摘要"
    assert result.focus_points_json == ["关注点1"]
    assert result.comment_text  # 回写文本应非空


def test_save_review_result_updates_existing(db_session):
    """二次保存应更新已有记录"""
    task = _create_task(db_session, "SAVE-UPD-001")
    hits = _create_rules_and_hits(db_session, task)

    service = ResultService(db_session)

    # 第一次保存
    result1 = service.save_review_result(
        task_id=task.id,
        overall_risk_level="中",
        summary_text="第一次摘要",
        focus_points=[],
        hits=hits,
    )

    # 第二次保存
    result2 = service.save_review_result(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="第二次摘要",
        focus_points=["新关注点"],
        hits=hits,
    )

    assert result1.id == result2.id  # 同一条记录
    assert result2.overall_risk_level == "高"
    assert result2.summary_text == "第二次摘要"


def test_save_review_result_updates_task_status(db_session):
    """保存结果应将任务状态变为 done"""
    task = _create_task(db_session, "SAVE-STATUS-001")
    hits = _create_rules_and_hits(db_session, task)

    service = ResultService(db_session)
    service.save_review_result(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="摘要",
        focus_points=[],
        hits=hits,
    )

    db_session.refresh(task)
    assert task.task_status == "done"
    assert task.write_status == "not_written"


def test_generate_comment_text_format(db_session):
    """回写文本应包含必要的格式要素"""
    task = _create_task(db_session, "COMMENT-FMT-001")
    hits = _create_rules_and_hits(db_session, task)

    service = ResultService(db_session)
    comment = service._generate_comment_text(
        overall_risk_level="高",
        summary_text="测试摘要文本",
        focus_points=["关注点A", "关注点B"],
        hits=hits,
    )

    # 应包含标题
    assert "【智能审查意见】" in comment
    # 应包含风险等级
    assert "总风险等级：高" in comment
    # 应包含摘要
    assert "测试摘要文本" in comment
    # 应包含风险事项
    assert "风险事项：" in comment
    # 应包含关注点
    assert "审批关注点：" in comment
    assert "关注点A" in comment
    assert "关注点B" in comment
    # 应包含签名
    assert "智能合同审查系统" in comment


def test_generate_comment_text_no_hits(db_session):
    """无命中时回写文本应说明未发现风险"""
    task = _create_task(db_session, "COMMENT-NO-HIT-001")

    service = ResultService(db_session)
    comment = service._generate_comment_text(
        overall_risk_level="低",
        summary_text="未发现明显风险",
        focus_points=[],
        hits=[],
    )

    assert "总风险等级：低" in comment
    assert "未发现明显风险" in comment
    # 无命中时不应有风险事项区块
    assert "风险事项" not in comment


def test_get_review_result(db_session):
    """查询审查结果"""
    task = _create_task(db_session, "GET-RESULT-001")
    hits = _create_rules_and_hits(db_session, task)

    service = ResultService(db_session)
    # 保存前查询应返回 None
    assert service.get_review_result(task.id) is None

    service.save_review_result(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="测试",
        focus_points=[],
        hits=hits,
    )
    # 保存后应能查询到
    result = service.get_review_result(task.id)
    assert result is not None
    assert result.overall_risk_level == "高"
