"""审查结果相关 Pydantic Schema —— 与前端 types/contract.ts 对齐。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.utils.constants import RiskLevel


class ReviewResultSave(BaseModel):
    """保存审查结果请求"""

    case_id: str = Field(..., description="审批实例 ID")
    overall_risk_level: RiskLevel = Field(..., description="整体风险等级")
    summary_text: str = Field(..., description="审查摘要")
    focus_points_json: list[str] = Field(default_factory=list, description="关注要点列表")
    comment_text: str = Field(default="", description="审查意见")


class ReviewResultResponse(BaseModel):
    """审查结果响应"""

    id: int
    task_id: int
    overall_risk_level: RiskLevel
    summary_text: str
    focus_points_json: list[str]
    comment_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleRunResponse(BaseModel):
    """规则执行结果响应"""

    case_id: str
    overall_risk_level: RiskLevel
    hits: list = Field(default_factory=list, description="规则命中列表")
    summary_text: str = ""
    focus_points: list[str] = Field(default_factory=list)
