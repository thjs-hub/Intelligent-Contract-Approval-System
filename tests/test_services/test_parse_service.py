"""M04 文档解析服务集成测试。"""

import pytest

from app.models.task import ApprovalTask
from app.services.attachment_service import AttachmentService
from app.services.parse_service import ParseService


async def _prepare_task_with_attachment(db_session, code: str = "PARSE-001"):
    """创建带附件的任务（通过 Mock 适配器下载）"""
    task = ApprovalTask(
        approval_code=code,
        approval_title="解析测试任务",
        applicant_name="测试人",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    # 下载附件（Mock 适配器会生成模拟 DOCX 内容）
    att_service = AttachmentService(db_session)
    await att_service.download_attachment(task.id, "att-001", "合同.docx")
    return task


@pytest.mark.asyncio
async def test_parse_contract_document_success(db_session, test_upload_dir):
    """有附件时解析应成功"""
    task = await _prepare_task_with_attachment(db_session, "PARSE-SUCC-001")

    service = ParseService(db_session)
    parse_record = await service.parse_contract_document(task.id)

    assert parse_record.parse_status == "success"
    assert parse_record.basic_info_json is not None
    assert parse_record.clause_info_json is not None

    # 任务状态应变为 parsing 后保持
    db_session.refresh(task)
    # 实际为 parsing（因为未触发后续审查）
    assert task.task_status in ("parsing",)


@pytest.mark.asyncio
async def test_parse_contract_document_no_attachment(db_session):
    """无附件时解析应失败并触发阻塞"""
    task = ApprovalTask(
        approval_code="PARSE-NOATT-001",
        approval_title="无附件任务",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    service = ParseService(db_session)
    parse_record = await service.parse_contract_document(task.id)

    assert parse_record.parse_status == "failed"
    assert "无可用附件" in (parse_record.parse_error or "")

    # 任务应被阻塞
    db_session.refresh(task)
    assert task.task_status == "blocked"


@pytest.mark.asyncio
async def test_parse_contract_document_creates_record(db_session, test_upload_dir):
    """解析应创建 ContractParse 记录"""
    from app.models.contract_parse import ContractParse

    task = await _prepare_task_with_attachment(db_session, "PARSE-CREATE-001")

    service = ParseService(db_session)
    await service.parse_contract_document(task.id)

    # 应有且仅有一条解析记录（一对一）
    records = db_session.query(ContractParse).filter_by(task_id=task.id).all()
    assert len(records) == 1
    assert records[0].parse_status == "success"


@pytest.mark.asyncio
async def test_parse_contract_document_idempotent(db_session, test_upload_dir):
    """重复调用解析应更新同一条记录，不创建新记录"""
    from app.models.contract_parse import ContractParse

    task = await _prepare_task_with_attachment(db_session, "PARSE-IDEM-001")

    service = ParseService(db_session)
    await service.parse_contract_document(task.id)
    await service.parse_contract_document(task.id)  # 重复调用

    records = db_session.query(ContractParse).filter_by(task_id=task.id).all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_get_parse_result(db_session, test_upload_dir):
    """查询解析结果"""
    task = await _prepare_task_with_attachment(db_session, "PARSE-GET-001")

    service = ParseService(db_session)
    # 解析前查询应返回 None
    assert service.get_parse_result(task.id) is None

    await service.parse_contract_document(task.id)
    # 解析后应能查询到
    result = service.get_parse_result(task.id)
    assert result is not None
    assert result.parse_status == "success"
