"""M08 评论回写服务单元测试。"""

import pytest

from app.models.review_result import ReviewResult
from app.models.task import ApprovalTask
from app.services.comment_service import CommentService


def _create_task_with_result(db_session, code: str = "COMMENT-001") -> ApprovalTask:
    """创建带审查结果的任务"""
    task = ApprovalTask(
        approval_code=code,
        approval_title="回写测试任务",
        task_status="done",
        write_status="not_written",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    result = ReviewResult(
        task_id=task.id,
        overall_risk_level="高",
        summary_text="测试摘要",
        focus_points_json=["关注点1"],
        comment_text="【智能审查意见】\n总风险等级：高\n测试内容",
    )
    db_session.add(result)
    db_session.commit()
    return task


@pytest.mark.asyncio
async def test_write_approval_comment_success(db_session):
    """正常回写应成功"""
    task = _create_task_with_result(db_session, "WRITE-SUCC-001")

    service = CommentService(db_session)
    comment_log = await service.write_approval_comment(task.id)

    assert comment_log.write_status == "success"
    assert comment_log.retry_count == 1
    assert comment_log.write_response_text  # 响应文本非空

    # 任务回写状态应更新
    db_session.refresh(task)
    assert task.write_status == "success"


@pytest.mark.asyncio
async def test_write_approval_comment_no_result_raises(db_session):
    """无审查结果时应抛 ValueError"""
    task = ApprovalTask(approval_code="WRITE-NO-RES-001")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    service = CommentService(db_session)
    with pytest.raises(ValueError, match="尚无审查结果"):
        await service.write_approval_comment(task.id)


@pytest.mark.asyncio
async def test_write_approval_comment_failure(db_session, monkeypatch):
    """回写失败应标记 failed"""
    task = _create_task_with_result(db_session, "WRITE-FAIL-001")

    # 模拟适配器回写失败
    from app.services.adapters.mock_adapter import MockApprovalAdapter

    async def _raise_write(self, instance_id, comment_text):
        raise RuntimeError("模拟回写失败")

    monkeypatch.setattr(MockApprovalAdapter, "write_comment", _raise_write)

    service = CommentService(db_session)
    comment_log = await service.write_approval_comment(task.id)

    assert comment_log.write_status == "failed"
    assert "模拟回写失败" in (comment_log.write_response_text or "")

    db_session.refresh(task)
    assert task.write_status == "failed"


@pytest.mark.asyncio
async def test_retry_write_increments_count(db_session):
    """重试应增加重试次数"""
    task = _create_task_with_result(db_session, "WRITE-RETRY-001")

    service = CommentService(db_session)

    # 第一次回写
    log1 = await service.write_approval_comment(task.id)
    assert log1.retry_count == 1

    # 第二次回写（模拟重试）
    log2 = await service.write_approval_comment(task.id)
    assert log2.retry_count == 2


@pytest.mark.asyncio
async def test_retry_write_method(db_session):
    """retry_write 方法应等价于 write_approval_comment"""
    task = _create_task_with_result(db_session, "WRITE-RETRY-METHOD-001")

    service = CommentService(db_session)
    log = await service.retry_write(task.id)

    assert log.write_status == "success"
    assert log.retry_count == 1


def test_get_comment_log(db_session):
    """查询任务回写日志"""
    task = _create_task_with_result(db_session, "WRITE-GET-001")

    service = CommentService(db_session)
    # 无日志时应返回 None
    assert service.get_comment_log(task.id) is None


def test_max_retry_constant():
    """MAX_RETRY 应为正整数"""
    assert CommentService.MAX_RETRY >= 1
    assert isinstance(CommentService.MAX_RETRY, int)
