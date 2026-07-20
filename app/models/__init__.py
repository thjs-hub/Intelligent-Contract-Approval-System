"""ORM 模型导出。

统一从此处导出所有 ORM 模型，便于 Alembic 自动发现和业务代码导入。
新增模型时必须在此处添加导出，否则 Alembic 迁移不会包含对应表。
"""

from app.models.attachment import ApprovalAttachment
from app.models.base import Base
from app.models.comment_log import CommentLog
from app.models.contract_parse import ContractParse
from app.models.review_result import ReviewResult
from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask
from app.models.task_log import TaskLog

__all__ = [
    "Base",
    "ApprovalTask",
    "ApprovalAttachment",
    "ContractParse",
    "ReviewRule",
    "RuleHit",
    "ReviewResult",
    "CommentLog",
    "TaskLog",
]
