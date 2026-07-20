"""合同附件相关 Pydantic Schema —— 与前端 types/contract.ts 对齐。"""

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentResponse(BaseModel):
    """附件信息响应"""

    id: int
    task_id: int
    file_name: str
    file_type: str
    file_path: str
    download_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachmentDownloadRequest(BaseModel):
    """附件下载请求"""

    instance_id: str = Field(..., description="审批实例 ID")
    attachment_id: str = Field(..., description="附件 ID")
    file_name: str = Field(..., description="文件名")
