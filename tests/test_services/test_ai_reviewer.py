"""P3-4 LLM 智能审查器单元测试。

测试 LLMReviewer 的核心功能:
  - Prompt 构建（包含合同全文、解析摘要、规则审查结果）
  - LLM 响应解析（标准 JSON、markdown 代码块、非 JSON 降级）
  - 摘要生成（LLM 不可用时降级到模板）
  - 配置不完整时的友好错误
  - Mock LLM 调用的端到端流程

测试策略:
  - LLM 客户端用 monkeypatch 替换为 Mock，避免真实 API 调用
  - 配置测试通过 monkeypatch settings 实现
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_reviewer import LLMReviewer


# ===== Mock LLM 响应 =====

MOCK_LLM_RESPONSE_JSON = '''{
  "risk_items": [
    {
      "risk_type": "权利义务不对等",
      "risk_level": "高",
      "description": "甲方有权单方面变更合同内容",
      "evidence": "第八条 甲方有权根据市场情况调整合同内容",
      "suggestion": "建议增加双方协商一致的前置条件"
    }
  ],
  "overall_assessment": "该合同甲方权利明显大于乙方",
  "missing_clauses": ["验收标准缺失"]
}'''

MOCK_LLM_RESPONSE_MARKDOWN = '''```json
{
  "risk_items": [
    {
      "risk_type": "模糊表述",
      "risk_level": "中",
      "description": "合同含'视情况而定'表述",
      "evidence": "按实际情况确定",
      "suggestion": "建议明确具体标准"
    }
  ],
  "overall_assessment": "合同存在模糊表述",
  "missing_clauses": []
}
```'''

MOCK_LLM_RESPONSE_NON_JSON = "这是一段非 JSON 格式的 LLM 响应文本。"


@pytest.fixture
def llm_reviewer():
    """LLMReviewer 实例"""
    return LLMReviewer()


@pytest.fixture
def configured_llm_reviewer(monkeypatch):
    """配置完整的 LLMReviewer（endpoint 和 api_key 已设置）"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_ENDPOINT", "https://api.test.com/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    return LLMReviewer()


class TestLLMReviewerBuildPrompt:
    """Prompt 构建测试"""

    def test_build_prompt_contains_contract_text(self, llm_reviewer):
        """Prompt 应包含合同全文"""
        contract_text = "这是一份测试合同，合同金额100万元。"
        prompt = llm_reviewer._build_prompt(
            contract_text=contract_text,
            parse_result={"basic_info": {}, "clause_info": {}},
            rule_review_result=None,
        )
        assert contract_text in prompt

    def test_build_prompt_contains_parse_summary(self, llm_reviewer):
        """Prompt 应包含解析结果摘要"""
        parse_result = {
            "basic_info": {
                "contract_amount": {
                    "extracted": True,
                    "value": "100万元",
                }
            },
            "clause_info": {},
        }
        prompt = llm_reviewer._build_prompt(
            contract_text="合同文本",
            parse_result=parse_result,
            rule_review_result=None,
        )
        assert "contract_amount" in prompt
        assert "100万元" in prompt

    def test_build_prompt_contains_rule_review_result(self, llm_reviewer):
        """Prompt 应包含规则审查结果摘要"""
        rule_result = {
            "hits": [
                {"rule_name": "违约责任规则"},
                {"rule_name": "预付款规则"},
            ]
        }
        prompt = llm_reviewer._build_prompt(
            contract_text="合同文本",
            parse_result={"basic_info": {}, "clause_info": {}},
            rule_review_result=rule_result,
        )
        assert "违约责任规则" in prompt
        assert "预付款规则" in prompt
        assert "共命中 2 条规则" in prompt

    def test_build_prompt_truncates_long_contract(self, llm_reviewer):
        """超长合同文本应被截断"""
        long_text = "合同内容" * 5000  # 远超 8000 字符
        prompt = llm_reviewer._build_prompt(
            contract_text=long_text,
            parse_result={"basic_info": {}, "clause_info": {}},
            rule_review_result=None,
        )
        assert "[合同文本已截断" in prompt
        assert len(prompt) < len(long_text) + 5000  # 应明显短于原文


class TestLLMReviewerParseResponse:
    """LLM 响应解析测试"""

    def test_parse_standard_json(self, llm_reviewer):
        """标准 JSON 响应应正确解析"""
        result = llm_reviewer._parse_response(MOCK_LLM_RESPONSE_JSON)
        assert len(result["risk_items"]) == 1
        assert result["risk_items"][0]["risk_type"] == "权利义务不对等"
        assert result["overall_assessment"] == "该合同甲方权利明显大于乙方"
        assert result["missing_clauses"] == ["验收标准缺失"]

    def test_parse_markdown_wrapped_json(self, llm_reviewer):
        """markdown 代码块包裹的 JSON 应正确提取"""
        result = llm_reviewer._parse_response(MOCK_LLM_RESPONSE_MARKDOWN)
        assert len(result["risk_items"]) == 1
        assert result["risk_items"][0]["risk_type"] == "模糊表述"

    def test_parse_non_json_returns_raw_text(self, llm_reviewer):
        """非 JSON 响应应返回原始文本作为评估"""
        result = llm_reviewer._parse_response(MOCK_LLM_RESPONSE_NON_JSON)
        assert result["risk_items"] == []
        assert MOCK_LLM_RESPONSE_NON_JSON in result["overall_assessment"]
        assert "parse_error" in result

    def test_parse_empty_response(self, llm_reviewer):
        """空响应应返回空结构"""
        result = llm_reviewer._parse_response("")
        assert result["risk_items"] == []
        assert "parse_error" in result

    def test_parse_response_ensures_required_fields(self, llm_reviewer):
        """解析结果应确保包含所有必需字段"""
        # JSON 缺少部分字段
        partial_json = '{"risk_items": []}'
        result = llm_reviewer._parse_response(partial_json)
        assert "risk_items" in result
        assert "overall_assessment" in result
        assert "missing_clauses" in result


class TestLLMReviewerDeepAnalysis:
    """deep_analysis 完整流程测试（使用 Mock LLM）"""

    @pytest.mark.asyncio
    async def test_deep_analysis_with_mock_llm(
        self, configured_llm_reviewer, monkeypatch
    ):
        """Mock LLM 返回标准 JSON 时应正确解析"""
        # Mock _call_llm_async 返回标准 JSON
        async def mock_call(prompt: str) -> str:
            return MOCK_LLM_RESPONSE_JSON

        monkeypatch.setattr(configured_llm_reviewer, "_call_llm_async", mock_call)

        result = await configured_llm_reviewer.deep_analysis(
            contract_text="合同文本",
            parse_result={"basic_info": {}, "clause_info": {}},
            rule_review_result=None,
        )

        assert len(result["risk_items"]) == 1
        assert result["risk_items"][0]["risk_type"] == "权利义务不对等"
        assert result["model"] == "test-model"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_deep_analysis_returns_error_on_failure(
        self, llm_reviewer, monkeypatch
    ):
        """LLM 调用失败时应返回 error 信息但不抛异常"""
        async def mock_call(prompt: str) -> str:
            raise RuntimeError("LLM API 不可用")

        monkeypatch.setattr(llm_reviewer, "_call_llm_async", mock_call)

        result = await llm_reviewer.deep_analysis(
            contract_text="合同文本",
            parse_result={"basic_info": {}, "clause_info": {}},
            rule_review_result=None,
        )

        assert result["risk_items"] == []
        assert "error" in result
        assert "LLM API 不可用" in result["error"]


class TestLLMReviewerGenerateSummary:
    """generate_summary 摘要生成测试"""

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm(self, configured_llm_reviewer, monkeypatch):
        """LLM 可用时应返回 LLM 生成的摘要"""
        async def mock_call(prompt: str) -> str:
            return "这是 LLM 生成的审查摘要。"

        monkeypatch.setattr(configured_llm_reviewer, "_call_llm_async", mock_call)

        summary = await configured_llm_reviewer.generate_summary(
            rule_hits=[],
            ai_risk_items=[],
            overall_risk_level="中",
        )
        assert "LLM 生成" in summary

    @pytest.mark.asyncio
    async def test_generate_summary_fallback_on_failure(self, llm_reviewer, monkeypatch):
        """LLM 不可用时应降级到模板摘要"""
        async def mock_call(prompt: str) -> str:
            raise RuntimeError("LLM 不可用")

        monkeypatch.setattr(llm_reviewer, "_call_llm_async", mock_call)

        summary = await llm_reviewer.generate_summary(
            rule_hits=["规则1", "规则2"],
            ai_risk_items=["风险1", "风险2", "风险3"],
            overall_risk_level="高",
        )
        # 应包含规则数和 AI 风险数
        assert "2" in summary  # 规则数
        assert "3" in summary  # AI 风险数
        assert "高" in summary


class TestLLMReviewerConfig:
    """配置测试"""

    def test_config_not_complete_raises(self, llm_reviewer):
        """配置不完整时应抛 RuntimeError"""
        with pytest.raises(RuntimeError, match="LLM 配置不完整"):
            llm_reviewer._get_client()

    def test_config_complete_initializes_client(
        self, configured_llm_reviewer, monkeypatch
    ):
        """配置完整时应能初始化客户端（Mock openai 模块）"""
        # Mock openai 模块
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        # 注入 Mock 模块
        import sys
        sys.modules["openai"] = mock_openai

        try:
            client = configured_llm_reviewer._get_client()
            assert client is mock_client
        finally:
            # 清理
            if "openai" in sys.modules:
                del sys.modules["openai"]


class TestLLMReviewerExtractRuleName:
    """_extract_rule_name 辅助方法测试"""

    def test_extract_rule_name_from_dict(self, llm_reviewer):
        """从字典提取规则名"""
        hit = {"rule_name": "违约责任规则", "rule_code": "R001"}
        assert llm_reviewer._extract_rule_name(hit) == "违约责任规则"

    def test_extract_rule_name_from_dict_with_code_only(self, llm_reviewer):
        """字典只有 rule_code 时应返回 rule_code"""
        hit = {"rule_code": "R001"}
        assert llm_reviewer._extract_rule_name(hit) == "R001"

    def test_extract_rule_name_from_object_with_rule(self, llm_reviewer):
        """从带 rule 属性的对象提取规则名"""
        mock_rule = MagicMock()
        mock_rule.rule_name = "测试规则"
        mock_hit = MagicMock()
        mock_hit.rule = mock_rule

        assert llm_reviewer._extract_rule_name(mock_hit) == "测试规则"
