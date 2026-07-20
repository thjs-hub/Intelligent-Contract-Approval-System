"""审批任务相关 Pydantic Schema —— 与前端 types/contract.ts 对齐。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.utils.constants import TaskStatus, WriteStatus


class ApprovalTaskBase(BaseModel):
    """审批任务公共字段"""

    approval_code: str = Field(..., description="审批编号")
    approval_title: str = Field(..., description="审批标题")
    applicant_name: str = Field(..., description="申请人姓名")


class ApprovalTaskCreate(ApprovalTaskBase):
    """创建审批任务请求"""

    pass


class ApprovalTaskResponse(ApprovalTaskBase):
    """审批任务响应"""

    id: int
    task_status: TaskStatus
    write_status: WriteStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContractParseResponse(BaseModel):
    """合同解析结果响应"""

    id: int
    task_id: int
    basic_info_json: dict = Field(default_factory=dict)
    clause_info_json: dict = Field(default_factory=dict)
    parse_status: str
    parse_error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentLogResponse(BaseModel):
    """回写评论日志响应"""

    id: int
    task_id: int
    write_status: WriteStatus
    write_response_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskLogResponse(BaseModel):
    """任务运行日志响应"""

    id: int
    task_id: int
    log_level: str
    log_type: str
    log_content: str
    created_at: datetime

    model_config = {"from_attributes": True}
