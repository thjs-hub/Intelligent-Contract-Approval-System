"""合同附件管理 API (M02)。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.attachment import AttachmentResponse
from app.services.attachment_service import AttachmentService
from app.utils.response import error_response, success_response

router = APIRouter()


class AttachmentDownloadRequest(BaseModel):
    """附件下载请求体"""

    task_id: int = Field(..., description="任务 ID")
    attachment_id: str = Field(..., description="外部附件 ID")
    file_name: str = Field(..., description="文件名")


@router.post("/download")
async def download_attachment(
    req: AttachmentDownloadRequest,
    db: Session = Depends(get_db),
):
    """接口: download_contract_attachment(instance_id, attachment_id, file_name)

    下载单个附件并保存到本地。
    """
    service = AttachmentService(db)
    try:
        attachment = await service.download_attachment(
            task_id=req.task_id,
            attachment_id=req.attachment_id,
            file_name=req.file_name,
        )
        data = AttachmentResponse.model_validate(attachment).model_dump(mode="json")
        return success_response(data=data, message="附件下载完成")
    except Exception as e:
        return error_response(f"附件下载失败: {e}")


@router.post("/download_all/{task_id}")
async def download_all_attachments(
    task_id: int,
    db: Session = Depends(get_db),
):
    """下载某审批单的全部附件"""
    service = AttachmentService(db)
    try:
        attachments = await service.download_all_for_task(task_id)
        data = [
            AttachmentResponse.model_validate(a).model_dump(mode="json")
            for a in attachments
        ]
        return success_response(data=data, message=f"共下载 {len(data)} 个附件")
    except Exception as e:
        return error_response(f"批量下载附件失败: {e}")


@router.get("/")
def list_attachments(
    task_id: int = Query(..., description="任务 ID"),
    db: Session = Depends(get_db),
):
    """查询任务的附件列表"""
    service = AttachmentService(db)
    attachments = service.list_attachments(task_id)
    data = [
        AttachmentResponse.model_validate(a).model_dump(mode="json")
        for a in attachments
    ]
    return success_response(data=data, message=f"共 {len(data)} 个附件")


@router.get("/{attachment_id}")
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
):
    """查询单个附件详情"""
    service = AttachmentService(db)
    attachment = service.get_attachment(attachment_id)
    if not attachment:
        return error_response(f"附件不存在: {attachment_id}", code=404)
    data = AttachmentResponse.model_validate(attachment).model_dump(mode="json")
    return success_response(data=data)
