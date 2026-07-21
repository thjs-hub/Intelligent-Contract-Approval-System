"""合同文档解析 API (M04)。"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.attachment import ApprovalAttachment
from app.models.task import ApprovalTask
from app.schemas.task import ContractParseResponse
from app.services.file_storage import FileStorageService
from app.services.parse_service import ParseService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """直接上传合同文件（绕过外部审批系统，开发调试用）。

    创建虚拟 ApprovalTask + 保存文件 + 创建 ApprovalAttachment，
    后续解析→审查→AI 流程无需任何改动。
    """
    content = await file.read()
    file_name = file.filename or "unnamed_upload"

    approval_code = f"DIRECT_UPLOAD_{uuid.uuid4().hex[:12]}"
    task = ApprovalTask(
        approval_code=approval_code,
        approval_title=file_name,
        applicant_name="直接上传",
        task_status="pending",
        write_status="not_written",
    )
    db.add(task)
    db.flush()

    storage = FileStorageService()
    file_path = await storage.save_file(task.id, file_name, content)
    file_type = FileStorageService.detect_file_type(file_name)
    file_md5 = FileStorageService.compute_md5(content)

    attachment = ApprovalAttachment(
        task_id=task.id,
        file_name=file_name,
        file_type=file_type,
        file_path=file_path,
        file_size=len(content),
        file_md5=file_md5,
        download_status="success",
    )
    db.add(attachment)
    db.commit()

    return success_response(
        data={"task_id": task.id, "approval_code": task.approval_code},
        message="文件上传成功",
    )


@router.post("/parse/{task_id}")
async def parse_contract_document(
    task_id: int,
    db: Session = Depends(get_db),
):
    """接口: parse_contract_document(document_id)

    触发合同文档解析。会自动选择已下载附件进行解析，
    图片/扫描 PDF 会自动路由到 M05 OCR 模块。
    """
    service = ParseService(db)
    try:
        parse_record = await service.parse_contract_document(task_id)
        data = ContractParseResponse.model_validate(parse_record).model_dump(mode="json")
        return success_response(data=data, message=f"文档解析完成: {parse_record.parse_status}")
    except Exception as e:
        return error_response(f"文档解析失败: {e}")


@router.get("/{task_id}")
def get_parse_result(
    task_id: int,
    db: Session = Depends(get_db),
):
    """查询任务的解析结果"""
    service = ParseService(db)
    parse_record = service.get_parse_result(task_id)
    if not parse_record:
        return error_response(f"任务 {task_id} 暂无解析结果", code=404)
    data = ContractParseResponse.model_validate(parse_record).model_dump(mode="json")
    return success_response(data=data)
