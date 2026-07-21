"""M03 唯一性去重服务单元测试。"""

from app.models.task import ApprovalTask
from app.services.dedup_service import DedupService


def test_dedup_creates_new_task(db_session):
    """全新 approval_code 应创建新任务"""
    task, is_new = DedupService.check_and_resolve(
        db_session,
        approval_code="DEDUP-NEW-001",
        approval_title="新任务",
        applicant_name="张三",
    )
    db_session.commit()

    assert is_new is True
    assert task.id is not None
    assert task.approval_code == "DEDUP-NEW-001"
    assert task.approval_title == "新任务"
    assert task.task_status == "pending"
    assert task.write_status == "not_written"


def test_dedup_returns_existing_task(db_session):
    """重复 approval_code 应返回已有任务，不创建新记录"""
    # 第一次创建
    task1, is_new1 = DedupService.check_and_resolve(
        db_session, approval_code="DEDUP-DUP-001", approval_title="原标题"
    )
    db_session.commit()

    # 第二次调用同一 code
    task2, is_new2 = DedupService.check_and_resolve(
        db_session, approval_code="DEDUP-DUP-001", approval_title="新标题"
    )
    db_session.commit()

    assert is_new1 is True
    assert is_new2 is False
    assert task1.id == task2.id  # 同一条记录


def test_dedup_updates_fields(db_session):
    """重复 code 带更新字段应更新原记录"""
    DedupService.check_and_resolve(
        db_session,
        approval_code="DEDUP-UPD-001",
        approval_title="原标题",
        applicant_name="原申请人",
    )
    db_session.commit()

    # 更新
    task, is_new = DedupService.check_and_resolve(
        db_session,
        approval_code="DEDUP-UPD-001",
        approval_title="新标题",
        applicant_name="新申请人",
    )
    db_session.commit()

    assert is_new is False
    assert task.approval_title == "新标题"
    assert task.applicant_name == "新申请人"


def test_dedup_none_value_does_not_overwrite(db_session):
    """update_fields 中 None 值不应覆盖原值"""
    DedupService.check_and_resolve(
        db_session,
        approval_code="DEDUP-NONE-001",
        approval_title="原标题",
        applicant_name="原申请人",
    )
    db_session.commit()

    # 传入 None 不应覆盖
    task, _ = DedupService.check_and_resolve(
        db_session,
        approval_code="DEDUP-NONE-001",
        approval_title=None,
        applicant_name=None,
    )
    db_session.commit()

    assert task.approval_title == "原标题"
    assert task.applicant_name == "原申请人"


def test_dedup_multiple_codes(db_session):
    """多个不同 approval_code 应各自创建独立任务"""
    codes = [f"DEDUP-MULTI-{i:03d}" for i in range(5)]
    for code in codes:
        DedupService.check_and_resolve(db_session, approval_code=code)
    db_session.commit()

    tasks = db_session.query(ApprovalTask).all()
    assert len(tasks) == 5
    assert {t.approval_code for t in tasks} == set(codes)
