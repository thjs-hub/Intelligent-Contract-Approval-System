"""M10 异常阻塞处理单元测试。"""

import pytest

from app.models.task import ApprovalTask
from app.services.block_handler import BlockHandler
from app.services.task_log_service import log_error, log_info


def _create_task(db_session, status: str = "parsing") -> ApprovalTask:
    """创建测试用任务"""
    task = ApprovalTask(
        approval_code=f"TEST-BLOCK-{status}",
        approval_title="阻塞测试任务",
        task_status=status,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_trigger_block_changes_status(db_session):
    """触发阻塞应将任务状态变为 blocked"""
    task = _create_task(db_session, status="parsing")
    BlockHandler.trigger_block(db_session, task.id, reason="测试阻塞", module="M04")

    db_session.refresh(task)
    assert task.task_status == "blocked"
    assert "测试阻塞" in (task.block_reason or "")


def test_trigger_block_logs_error(db_session):
    """触发阻塞应记录 ERROR 日志"""
    from app.services.task_log_service import get_task_logs

    task = _create_task(db_session, status="reviewing")
    BlockHandler.trigger_block(db_session, task.id, reason="审查失败", module="M06")

    logs = get_task_logs(db_session, task.id, level="ERROR")
    assert any("任务阻塞" in (log.log_content or "") for log in logs)


def test_trigger_block_nonexistent_task_no_error(db_session):
    """对不存在的任务触发阻塞不应抛异常"""
    # 不应抛异常
    BlockHandler.trigger_block(db_session, task_id=99999, reason="任务不存在")


def test_retry_task_from_parsing_stage(db_session):
    """附件/解析/OCR 错误应从 parsing 阶段重试"""
    task = _create_task(db_session, status="parsing")
    # 模拟附件下载失败，指定 module=M02
    BlockHandler.trigger_block(
        db_session, task.id, reason="附件下载失败", module="M02"
    )
    db_session.commit()

    retry_from = BlockHandler.retry_task(db_session, task.id)
    assert retry_from == "parsing"

    db_session.refresh(task)
    assert task.task_status == "parsing"
    assert task.block_reason is None  # 阻塞原因应清除


def test_retry_task_from_reviewing_stage(db_session):
    """审查/回写错误应从 reviewing 阶段重试"""
    task = _create_task(db_session, status="reviewing")
    # 模拟审查失败，指定 module=M06
    BlockHandler.trigger_block(
        db_session, task.id, reason="规则审查异常", module="M06"
    )
    db_session.commit()

    retry_from = BlockHandler.retry_task(db_session, task.id)
    assert retry_from == "reviewing"

    db_session.refresh(task)
    assert task.task_status == "reviewing"


def test_retry_non_blocked_task_raises(db_session):
    """对非 blocked 状态任务重试应抛 ValueError"""
    task = _create_task(db_session, status="done")
    with pytest.raises(ValueError, match="不处于阻塞状态"):
        BlockHandler.retry_task(db_session, task.id)


def test_retry_nonexistent_task_raises(db_session):
    """对不存在的任务重试应抛 ValueError"""
    with pytest.raises(ValueError, match="任务不存在"):
        BlockHandler.retry_task(db_session, task_id=99999)


def test_get_blocked_tasks(db_session):
    """获取所有阻塞任务"""
    # 创建 3 个任务，2 个 blocked
    t1 = ApprovalTask(approval_code="B1", task_status="blocked", block_reason="原因1")
    t2 = ApprovalTask(approval_code="B2", task_status="blocked", block_reason="原因2")
    t3 = ApprovalTask(approval_code="N1", task_status="pending")
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    blocked = BlockHandler.get_blocked_tasks(db_session)
    assert len(blocked) == 2
    assert all(t.task_status == "blocked" for t in blocked)
