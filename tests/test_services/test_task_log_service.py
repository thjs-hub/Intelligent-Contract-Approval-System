"""M09 任务日志服务单元测试。"""

import pytest

from app.models.task import ApprovalTask
from app.services.task_log_service import (
    get_all_logs,
    get_task_logs,
    log_error,
    log_info,
    log_warn,
)


def _create_task(db_session) -> ApprovalTask:
    """创建测试用任务"""
    task = ApprovalTask(
        approval_code="TEST-LOG-001",
        approval_title="日志测试任务",
        applicant_name="测试人",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_log_info_writes_to_db(db_session):
    """INFO 级别日志应写入数据库"""
    task = _create_task(db_session)
    log_info(db_session, task.id, "M01", "测试 INFO 日志")
    db_session.commit()

    logs = get_task_logs(db_session, task.id)
    assert len(logs) >= 1
    latest = logs[0]
    assert latest.log_level == "INFO"
    assert latest.log_type == "M01"
    assert "测试 INFO 日志" in latest.log_content


def test_log_warn_writes_to_db(db_session):
    """WARN 级别日志应写入数据库"""
    task = _create_task(db_session)
    log_warn(db_session, task.id, "M04", "解析耗时偏长")
    db_session.commit()

    logs = get_task_logs(db_session, task.id, level="WARN")
    assert len(logs) >= 1
    assert logs[0].log_level == "WARN"


def test_log_error_writes_to_db(db_session):
    """ERROR 级别日志应写入数据库"""
    task = _create_task(db_session)
    log_error(db_session, task.id, "M02", "附件下载失败")
    db_session.commit()

    logs = get_task_logs(db_session, task.id, level="ERROR")
    assert len(logs) >= 1
    assert logs[0].log_level == "ERROR"


def test_get_task_logs_filters_by_module(db_session):
    """按模块过滤日志"""
    task = _create_task(db_session)
    log_info(db_session, task.id, "M01", "M01 日志")
    log_info(db_session, task.id, "M04", "M04 日志")
    db_session.commit()

    m01_logs = get_task_logs(db_session, task.id, log_type="M01")
    assert all(log.log_type == "M01" for log in m01_logs)
    assert len(m01_logs) >= 1


def test_get_all_logs_returns_across_tasks(db_session):
    """全系统日志查询应跨任务返回"""
    task1 = ApprovalTask(approval_code="T1", approval_title="任务1")
    task2 = ApprovalTask(approval_code="T2", approval_title="任务2")
    db_session.add_all([task1, task2])
    db_session.commit()
    db_session.refresh(task1)
    db_session.refresh(task2)

    log_info(db_session, task1.id, "M01", "任务1 日志")
    log_info(db_session, task2.id, "M01", "任务2 日志")
    db_session.commit()

    all_logs = get_all_logs(db_session, limit=100)
    assert len(all_logs) >= 2


def test_log_truncates_long_content(db_session):
    """超长日志内容应被截断"""
    task = _create_task(db_session)
    long_content = "x" * 10000  # 超过 5000 字符上限
    log_info(db_session, task.id, "M01", long_content)
    db_session.commit()

    logs = get_task_logs(db_session, task.id)
    latest = logs[0]
    assert len(latest.log_content) <= 5000


def test_log_failure_does_not_raise(db_session, monkeypatch):
    """日志写入失败时不应抛异常"""
    task = _create_task(db_session)

    # 模拟 db.add 抛异常
    original_add = db_session.add

    def _raise_on_add(obj):
        raise RuntimeError("模拟数据库故障")

    monkeypatch.setattr(db_session, "add", _raise_on_add)
    # 不应抛异常
    log_info(db_session, task.id, "M01", "不应抛异常的日志")

    # 恢复并提交
    monkeypatch.setattr(db_session, "add", original_add)
    db_session.commit()
