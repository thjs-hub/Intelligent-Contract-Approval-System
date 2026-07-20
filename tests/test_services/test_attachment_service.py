"""M02 附件管理服务单元测试。"""

import pytest

from app.models.attachment import ApprovalAttachment
from app.models.task import ApprovalTask
from app.services.attachment_service import AttachmentService


def _create_task(db_session, code: str = "ATT-001") -> ApprovalTask:
    """创建测试用任务"""
    task = ApprovalTask(
        approval_code=code,
        approval_title="附件测试任务",
        applicant_name="测试人",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_download_attachment_success(db_session, test_upload_dir):
    """正常下载附件应成功"""
    task = _create_task(db_session, "ATT-SUCC-001")
    service = AttachmentService(db_session)

    attachment = await service.download_attachment(
        task_id=task.id,
        attachment_id="att-001",
        file_name="合同.docx",
    )

    assert attachment.download_status == "success"
    assert attachment.file_path is not None
    assert attachment.file_size > 0
    assert attachment.file_md5  # MD5 非空
    assert attachment.file_type == "docx"
    assert attachment.external_attachment_id == "att-001"


@pytest.mark.asyncio
async def test_download_attachment_failure_triggers_block(db_session, monkeypatch, test_upload_dir):
    """下载失败应触发 M10 阻塞"""
    task = _create_task(db_session, "ATT-FAIL-001")

    # 模拟适配器下载失败
    from app.services.adapters.mock_adapter import MockApprovalAdapter

    async def _raise_download(self, attachment_id):
        raise RuntimeError("模拟下载失败")

    monkeypatch.setattr(MockApprovalAdapter, "download_attachment", _raise_download)

    service = AttachmentService(db_session)
    attachment = await service.download_attachment(
        task_id=task.id,
        attachment_id="att-fail",
        file_name="failed.docx",
    )

    assert attachment.download_status == "failed"
    assert "模拟下载失败" in (attachment.download_error or "")

    # 任务应变为 blocked
    db_session.refresh(task)
    assert task.task_status == "blocked"


@pytest.mark.asyncio
async def test_download_all_for_task(db_session, test_upload_dir):
    """批量下载某任务的所有附件"""
    task = _create_task(db_session, "ATT-ALL-001")
    service = AttachmentService(db_session)

    attachments = await service.download_all_for_task(task.id)

    # Mock 适配器预置 2 个附件
    assert len(attachments) == 2
    for att in attachments:
        assert att.download_status == "success"


@pytest.mark.asyncio
async def test_list_attachments(db_session, test_upload_dir):
    """查询任务附件列表"""
    task = _create_task(db_session, "ATT-LIST-001")
    service = AttachmentService(db_session)

    # 先下载 2 个附件
    await service.download_attachment(task.id, "att-1", "file1.docx")
    await service.download_attachment(task.id, "att-2", "file2.pdf")

    attachments = service.list_attachments(task.id)
    assert len(attachments) == 2


@pytest.mark.asyncio
async def test_get_attachment_by_id(db_session, test_upload_dir):
    """按 ID 查询单个附件"""
    task = _create_task(db_session, "ATT-GET-001")
    service = AttachmentService(db_session)

    created = await service.download_attachment(task.id, "att-x", "find.docx")
    found = service.get_attachment(created.id)

    assert found is not None
    assert found.id == created.id
    assert found.file_name == "find.docx"


def test_get_attachment_not_found(db_session):
    """查询不存在的附件应返回 None"""
    service = AttachmentService(db_session)
    assert service.get_attachment(99999) is None
