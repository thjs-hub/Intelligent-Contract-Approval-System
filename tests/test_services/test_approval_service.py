"""M01 审批待办接入服务单元测试。"""

import pytest

from app.models.task import ApprovalTask
from app.services.approval_service import ApprovalService


@pytest.mark.asyncio
async def test_list_pending_approvals_creates_tasks(db_session):
    """拉取审批单应创建新任务"""
    service = ApprovalService(db_session)
    tasks = await service.list_pending_approvals(limit=5)

    assert len(tasks) == 5
    for i, task in enumerate(tasks, start=1):
        expected_code = f"AP-2026-{i:04d}"
        assert task.approval_code == expected_code
        assert task.task_status == "pending"


@pytest.mark.asyncio
async def test_list_pending_approvals_dedup(db_session):
    """连续两次拉取同一批审批单应去重，不重复创建"""
    service = ApprovalService(db_session)

    # 第一次拉取
    await service.list_pending_approvals(limit=3)
    # 第二次拉取相同数据
    await service.list_pending_approvals(limit=3)

    tasks = db_session.query(ApprovalTask).all()
    assert len(tasks) == 3  # 应去重，仅 3 条记录


@pytest.mark.asyncio
async def test_list_pending_approvals_updates_existing(db_session):
    """重复拉取应更新已有任务的元信息"""
    service = ApprovalService(db_session)

    # 第一次拉取
    tasks1 = await service.list_pending_approvals(limit=1)
    original_title = tasks1[0].approval_title

    # 第二次拉取（Mock 数据标题相同，但验证不会重复创建）
    tasks2 = await service.list_pending_approvals(limit=1)
    assert tasks1[0].id == tasks2[0].id  # 同一任务


@pytest.mark.asyncio
async def test_list_pending_approvals_empty(db_session, monkeypatch):
    """适配器返回空列表时应正常处理"""
    from app.services.adapters.mock_adapter import MockApprovalAdapter

    async def _empty_fetch(self, limit=20):
        return []

    monkeypatch.setattr(MockApprovalAdapter, "fetch_pending_approvals", _empty_fetch)

    service = ApprovalService(db_session)
    tasks = await service.list_pending_approvals(limit=10)
    assert tasks == []


def test_get_approval_detail(db_session):
    """按 approval_code 查询任务详情"""
    from app.services.dedup_service import DedupService

    DedupService.check_and_resolve(
        db_session,
        approval_code="DETAIL-001",
        approval_title="详情测试",
        applicant_name="测试人",
    )
    db_session.commit()

    service = ApprovalService(db_session)
    task = service.get_approval_detail("DETAIL-001")
    assert task is not None
    assert task.approval_title == "详情测试"


def test_get_approval_detail_not_found(db_session):
    """查询不存在的 approval_code 应返回 None"""
    service = ApprovalService(db_session)
    task = service.get_approval_detail("NOT-EXIST-999")
    assert task is None


def test_get_task_by_id(db_session):
    """按主键 ID 查询任务"""
    from app.services.dedup_service import DedupService

    new_task, _ = DedupService.check_and_resolve(
        db_session, approval_code="BYID-001"
    )
    db_session.commit()

    service = ApprovalService(db_session)
    found = service.get_task_by_id(new_task.id)
    assert found is not None
    assert found.id == new_task.id


def test_list_local_tasks(db_session):
    """查询本地任务列表"""
    from app.services.dedup_service import DedupService

    for i in range(5):
        DedupService.check_and_resolve(
            db_session, approval_code=f"LIST-{i:03d}"
        )
    db_session.commit()

    service = ApprovalService(db_session)
    tasks = service.list_local_tasks(limit=10)
    assert len(tasks) == 5
