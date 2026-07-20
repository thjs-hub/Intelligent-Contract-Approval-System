"""合同附件相关 Pydantic Schema —— 与前端 types/contract.ts 对齐。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AttachmentResponse(BaseModel):
    """附件信息响应"""

    id: int
    task_id: int
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    file_md5: Optional[str] = None
    download_status: str
    download_error: Optional[str] = None
    external_attachment_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachmentDownloadRequest(BaseModel):
    """附件下载请求"""

    task_id: int = Field(..., description="任务 ID")
    attachment_id: str = Field(..., description="外部附件 ID")
    file_name: str = Field(..., description="文件名")
