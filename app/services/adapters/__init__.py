"""审批系统适配器包初始化。"""

from app.services.adapters.base import ApprovalSystemAdapter, get_approval_adapter
from app.services.adapters.mock_adapter import MockApprovalAdapter

__all__ = ["ApprovalSystemAdapter", "get_approval_adapter", "MockApprovalAdapter"]
