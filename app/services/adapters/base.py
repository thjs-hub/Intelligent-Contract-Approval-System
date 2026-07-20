"""审批系统适配器抽象基类与工厂。

为支持接入不同的企业审批系统（钉钉/飞书/企业微信/自研 OA），
定义统一的适配器接口。第二阶段仅实现 Mock 适配器，
真实适配器为第三阶段扩展点。
"""

from abc import ABC, abstractmethod
from typing import Any


class ApprovalSystemAdapter(ABC):
    """审批系统适配器抽象基类

    所有具体审批系统适配器（钉钉/飞书/企业微信/Mock）需实现此接口。
    上层 ApprovalService 通过此接口与外部审批系统交互，
    屏蔽不同审批系统的 API 差异。
    """

    @abstractmethod
    async def fetch_pending_approvals(self, limit: int = 20) -> list[dict[str, Any]]:
        """从外部审批系统拉取待处理审批单列表

        参数:
          limit: 拉取条数上限

        返回:
          审批单字典列表，每条至少包含:
            - approval_code: 审批编号
            - approval_title: 审批标题
            - applicant_name: 申请人姓名
            - attachment_count: 附件数量
        """
        ...

    @abstractmethod
    async def fetch_approval_detail(self, instance_id: str) -> dict[str, Any]:
        """从外部审批系统拉取单个审批单详情

        参数:
          instance_id: 审批实例 ID（即 approval_code）

        返回:
          审批单详情字典，至少包含:
            - approval_code: 审批编号
            - approval_title: 审批标题
            - applicant_name: 申请人
            - form_data: 表单数据字典
            - attachments: 附件列表 [{attachment_id, file_name, file_type}, ...]
            - status: 审批状态
        """
        ...

    @abstractmethod
    async def download_attachment(self, attachment_id: str) -> bytes:
        """下载审批单附件二进制内容

        参数:
          attachment_id: 外部附件 ID

        返回:
          附件文件二进制内容
        """
        ...

    @abstractmethod
    async def write_comment(
        self,
        instance_id: str,
        comment_text: str,
    ) -> dict[str, Any]:
        """向审批单评论区写入审查意见

        参数:
          instance_id: 审批实例 ID
          comment_text: 评论内容

        返回:
          审批系统返回的响应字典，至少包含 success 字段
        """
        ...


def get_approval_adapter() -> ApprovalSystemAdapter:
    """根据配置返回对应的审批系统适配器实例

    通过 settings.APPROVAL_ADAPTER 配置项切换:
      - "mock": Mock 审批适配器（第二阶段默认）
      - "dingtalk" / "feishu" / "wecom": 第三阶段扩展点

    返回:
      ApprovalSystemAdapter 实例
    """
    # 延迟导入避免循环依赖
    from app.core.config import settings
    from app.services.adapters.mock_adapter import MockApprovalAdapter

    adapter_type = getattr(settings, "APPROVAL_ADAPTER", "mock")
    if adapter_type == "mock":
        return MockApprovalAdapter()
    # ===== 第三阶段扩展点 =====
    # elif adapter_type == "dingtalk":
    #     from app.services.adapters.dingtalk_adapter import DingTalkApprovalAdapter
    #     return DingTalkApprovalAdapter()
    # elif adapter_type == "feishu":
    #     from app.services.adapters.feishu_adapter import FeishuApprovalAdapter
    #     return FeishuApprovalAdapter()
    # elif adapter_type == "wecom":
    #     from app.services.adapters.wecom_adapter import WeComApprovalAdapter
    #     return WeComApprovalAdapter()
    # TODO: 第三阶段实现真实审批系统适配器后取消上方注释
    raise ValueError(f"未知的审批系统适配器类型: {adapter_type}")
