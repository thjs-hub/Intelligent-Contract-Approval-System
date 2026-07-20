"""审查规则相关 Pydantic Schema —— 与前端 types/contract.ts 对齐。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.utils.constants import RiskLevel, RuleMatchMode


class ReviewRuleBase(BaseModel):
    """审查规则公共字段"""

    rule_code: str = Field(..., description="规则编码")
    rule_name: str = Field(..., description="规则名称")
    risk_level: RiskLevel = Field(..., description="风险等级")
    match_mode: RuleMatchMode = Field(..., description="匹配模式")
    match_text: str = Field(..., description="匹配文本")
    suggestion_text: str = Field(..., description="建议文本")


class ReviewRuleCreate(ReviewRuleBase):
    """创建审查规则请求"""

    pass


class ReviewRuleUpdate(BaseModel):
    """更新审查规则请求（所有字段可选）"""

    rule_code: str | None = None
    rule_name: str | None = None
    risk_level: RiskLevel | None = None
    match_mode: RuleMatchMode | None = None
    match_text: str | None = None
    suggestion_text: str | None = None
    rule_status: str | None = None


class ReviewRuleResponse(ReviewRuleBase):
    """审查规则响应"""

    id: int
    rule_status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleHitResponse(BaseModel):
    """规则命中结果响应"""

    id: int
    task_id: int
    rule_id: int
    evidence_text: str
    evidence_position: str
    hit_status: str
    created_at: datetime

    model_config = {"from_attributes": True}
