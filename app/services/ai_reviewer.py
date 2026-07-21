"""LLM 智能审查器 — 第三阶段实现（P3-4）。

接入大语言模型（LLM）进行非规则化的深度合同风险分析。
识别规则库无法覆盖的隐性风险：不平等条款、模糊表述、权利义务失衡、
缺失关键条款等。输出结构化的 AI 审查意见，与规则审查结果合并后统一呈现。

工作流程:
  1. 构建 Prompt（合同全文 + 解析结果 + 规则审查结果作为上下文）
  2. 调用 LLM API（OpenAI 兼容格式，支持通义千问/DeepSeek/智谱/OpenAI）
  3. 解析 LLM 响应为结构化审查意见

设计要点:
  - 客户端延迟初始化，避免应用启动时连接 LLM
  - 依赖未安装时返回友好错误信息，不抛异常（不阻塞主流程）
  - LLM 调用失败时降级返回空结果 + error 字段（AIOrchestrator 捕获后继续规则审查）
  - Prompt 中明确要求 JSON 输出，解析失败时返回原始文本作为评估
  - 支持生成审查摘要（替代第二阶段模板化摘要）

依赖（可选，未安装时降级）:
  pip install openai  # OpenAI Python SDK（兼容国产模型 API）
"""

import asyncio
import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("contract_review")


class LLMReviewer:
    """LLM 智能审查器

    工作流程:
      1. 构建 Prompt（合同全文 + 解析结果 + 规则审查结果）
      2. 调用 LLM API
      3. 解析 LLM 响应为结构化审查意见

    用法:
        reviewer = LLMReviewer()
        result = await reviewer.deep_analysis(
            contract_text=contract_text,
            parse_result={"basic_info": ..., "clause_info": ...},
            rule_review_result=rule_result,
        )
    """

    def __init__(self):
        """初始化 LLM 客户端配置

        客户端实例延迟创建（首次调用 _get_client 时初始化）
        """
        self._client: Any = None
        self._model: str = getattr(settings, "LLM_MODEL", "qwen-plus")
        self._endpoint: str = getattr(settings, "LLM_ENDPOINT", "")
        self._api_key: str = getattr(settings, "LLM_API_KEY", "")
        self._timeout: int = getattr(settings, "LLM_TIMEOUT", 60)
        self._max_tokens: int = getattr(settings, "LLM_MAX_TOKENS", 4096)
        self._temperature: float = getattr(settings, "LLM_TEMPERATURE", 0.1)

    def _get_client(self):
        """延迟初始化 OpenAI 兼容客户端

        依赖未安装或配置不完整时抛相应异常，由调用方捕获后降级处理
        """
        if self._client is None:
            if not self._endpoint or not self._api_key:
                raise RuntimeError(
                    "LLM 配置不完整: 请设置 LLM_ENDPOINT 和 LLM_API_KEY"
                )
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError(
                    "openai 未安装，请执行: pip install openai"
                ) from e
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._endpoint,
                timeout=self._timeout,
            )
        return self._client

    async def deep_analysis(
        self,
        contract_text: str,
        parse_result: dict[str, Any],
        rule_review_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LLM 深度风险分析

        参数:
          contract_text: 合同全文文本
          parse_result: M04 解析结果 (basic_info + clause_info)
          rule_review_result: M06 规则审查结果（已有风险项，供 LLM 参考）

        返回:
            {
                "risk_items": [           # LLM 识别的风险项
                    {
                        "risk_type": str,
                        "risk_level": "低"|"中"|"高",
                        "description": str,
                        "evidence": str,
                        "suggestion": str,
                    },
                    ...
                ],
                "overall_assessment": str,  # LLM 总体评估
                "missing_clauses": [str],   # 缺失的关键条款
                "model": str,               # 使用的模型名
                "error": str (可选),         # LLM 调用失败时的错误信息
            }
        """
        # 1. 构建 Prompt
        prompt = self._build_prompt(contract_text, parse_result, rule_review_result)

        # 2. 调用 LLM
        try:
            response_text = await self._call_llm_async(prompt)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                "risk_items": [],
                "overall_assessment": f"LLM 审查不可用: {e}",
                "missing_clauses": [],
                "model": self._model,
                "error": str(e),
            }

        # 3. 解析响应
        result = self._parse_response(response_text)
        result["model"] = self._model
        return result

    def _build_prompt(
        self,
        contract_text: str,
        parse_result: dict[str, Any],
        rule_review_result: dict[str, Any] | None,
    ) -> str:
        """构建 LLM 审查 Prompt

        Prompt 包含:
          - 系统角色设定（合同法务审查专家）
          - 合同解析摘要（M04 提取的字段和条款）
          - 规则审查结果摘要（已有命中，避免重复）
          - 合同全文（截断到 8000 字符避免 token 超限）
          - 审查维度指引（6 个维度）
          - 输出格式要求（JSON）
        """
        basic_info = parse_result.get("basic_info", {})
        clause_info = parse_result.get("clause_info", {})

        # 格式化解析结果摘要
        info_summary = self._format_parse_summary(basic_info, clause_info)

        # 格式化规则审查结果
        rule_summary = ""
        if rule_review_result:
            hits = rule_review_result.get("hits", [])
            rule_summary = f"\n\n【已有规则审查结果】\n"
            rule_summary += f"规则审查共命中 {len(hits)} 条规则。\n"
            for hit in hits[:10]:  # 最多提供 10 条
                # hits 可能是 RuleHit 对象或字典
                rule_name = self._extract_rule_name(hit)
                if rule_name:
                    rule_summary += f"- {rule_name}\n"

        # 合同全文截断（避免 token 超限）
        truncated_text = contract_text[:8000]
        if len(contract_text) > 8000:
            truncated_text += "\n\n[合同文本已截断，仅展示前 8000 字符]"

        prompt = f"""你是一位专业的合同法务审查专家。请对以下合同进行深度风险分析。

【合同解析摘要】
{info_summary}
{rule_summary}

【合同全文】
{truncated_text}

请从以下维度审查合同风险：
1. 权利义务对等性（甲方乙方的权利义务是否平衡）
2. 不平等条款（单方面权利、单方面解除权等）
3. 模糊表述（含"视情况""另行协商""原则上"等模糊用语）
4. 违约责任对等性（双方违约责任是否对等）
5. 缺失关键条款（验收标准、知识产权归属、保密条款等是否缺失）
6. 合规风险（是否违反法律法规强制性规定）

请以 JSON 格式输出审查结果，不要包含其他文字：
{{
  "risk_items": [
    {{
      "risk_type": "权利义务不对等",
      "risk_level": "高",
      "description": "甲方有权单方面变更合同内容，乙方无对应权利",
      "evidence": "第八条 甲方有权根据市场情况调整合同内容",
      "suggestion": "建议增加'变更需双方协商一致'的前置条件"
    }}
  ],
  "overall_assessment": "该合同整体风险较高，甲方权利明显大于乙方...",
  "missing_clauses": ["验收标准缺失", "知识产权归属未约定"]
}}"""
        return prompt

    def _format_parse_summary(
        self, basic_info: dict, clause_info: dict
    ) -> str:
        """格式化解析结果摘要"""
        lines: list[str] = []
        for field, info in basic_info.items():
            if isinstance(info, dict) and info.get("extracted"):
                value = info.get("value", "")
                if value:
                    lines.append(f"- {field}: {value}")
        for clause, info in clause_info.items():
            if isinstance(info, dict):
                status = "✓" if info.get("extracted") else "✗"
                lines.append(f"- {clause}: {status}")
        return "\n".join(lines) if lines else "（无解析结果）"

    def _extract_rule_name(self, hit: Any) -> str:
        """从 RuleHit 对象或字典中提取规则名"""
        if isinstance(hit, dict):
            return hit.get("rule_name", "") or hit.get("rule_code", "")
        # RuleHit ORM 对象
        if hasattr(hit, "rule") and hit.rule:
            return hit.rule.rule_name
        return getattr(hit, "rule_id", "未知规则")

    async def _call_llm_async(self, prompt: str) -> str:
        """调用 LLM API（异步包装）

        OpenAI SDK 是同步的，用 asyncio.to_thread 包装为异步，
        避免阻塞 FastAPI 事件循环
        """
        client = self._get_client()

        # 同步调用包装为异步
        def _sync_call() -> str:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是合同法务审查专家，请严格按JSON格式输出。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            return response.choices[0].message.content or ""

        return await asyncio.to_thread(_sync_call)

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """解析 LLM 响应为结构化数据

        处理以下情况:
          1. 标准 JSON 响应 → 直接解析
          2. markdown 代码块包裹的 JSON → 提取后解析
          3. 非 JSON 响应 → 返回原始文本作为评估 + parse_error 标记
        """
        if not response_text or not response_text.strip():
            return {
                "risk_items": [],
                "overall_assessment": "",
                "missing_clauses": [],
                "parse_error": "LLM 响应为空",
            }

        text = response_text.strip()

        # 处理可能的 markdown 代码块包裹
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            if end > start:
                text = text[start:end].strip()

        try:
            result = json.loads(text)
            # 确保字段完整
            result.setdefault("risk_items", [])
            result.setdefault("overall_assessment", "")
            result.setdefault("missing_clauses", [])
            return result

        except json.JSONDecodeError:
            # JSON 解析失败 → 返回原始文本作为评估
            return {
                "risk_items": [],
                "overall_assessment": response_text[:2000],
                "missing_clauses": [],
                "parse_error": "LLM 响应非标准 JSON 格式",
            }

    async def generate_summary(
        self,
        rule_hits: list,
        ai_risk_items: list,
        overall_risk_level: str,
    ) -> str:
        """用 LLM 生成审查摘要（替代第二阶段的模板化摘要）

        参数:
          rule_hits: 规则命中列表（RuleHit 对象或字典）
          ai_risk_items: AI 识别的风险项列表
          overall_risk_level: 总体风险等级

        返回:
          审查摘要文本。LLM 不可用时降级到模板摘要
        """
        # 格式化规则命中项（最多 5 条）
        rule_lines: list[str] = []
        for hit in rule_hits[:5]:
            rule_name = self._extract_rule_name(hit)
            if rule_name:
                rule_lines.append(f"- {rule_name}")

        # 格式化 AI 风险项（最多 5 条）
        ai_lines: list[str] = []
        for item in ai_risk_items[:5]:
            if isinstance(item, dict):
                risk_type = item.get("risk_type", "")
                description = item.get("description", "")
                ai_lines.append(f"- {risk_type}: {description}")

        prompt = f"""请为以下合同审查结果生成一段简洁的中文审查摘要（200字以内）：

总体风险等级：{overall_risk_level}
规则命中数：{len(rule_hits)}
AI 识别风险数：{len(ai_risk_items)}

规则命中项：
{chr(10).join(rule_lines) if rule_lines else "（无）"}

AI 识别风险项：
{chr(10).join(ai_lines) if ai_lines else "（无）"}

请直接输出摘要文本，不要包含其他内容。"""

        try:
            response_text = await self._call_llm_async(prompt)
            return response_text.strip()
        except Exception as e:
            logger.warning(f"LLM 摘要生成失败，降级到模板摘要: {e}")
            # LLM 不可用时降级到模板摘要
            return (
                f"经审查，该合同共发现 {len(rule_hits)} 项规则风险和 "
                f"{len(ai_risk_items)} 项 AI 识别风险，"
                f"总体风险等级为{overall_risk_level}。"
            )
