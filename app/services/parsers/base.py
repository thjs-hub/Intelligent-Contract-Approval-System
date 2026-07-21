"""文档解析器抽象基类与提取器 (M04)。

定义统一的文本提取器接口，第二阶段实现基于正则的 RegexTextExtractor。
第三阶段扩展点: NLPExtractor 基于 NER 模型进行字段抽取。

提取器职责:
  - extract_basic_info: 从全文中提取合同基本信息 (标题/编号/主体/金额/日期)
  - extract_clauses: 从全文中识别 8 类关键条款段落
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTextExtractor(ABC):
    """文本提取器抽象基类

    子类需实现 extract_basic_info 和 extract_clauses 方法。
    """

    @abstractmethod
    def extract_basic_info(self, text: str) -> dict[str, Any]:
        """从全文提取合同基本信息

        参数:
          text: 合同全文

        返回:
          字段字典，每个字段结构:
            {
              "value": str | None,        # 提取值
              "source_text": str | None,   # 原文证据片段
              "position": str | None,      # 位置标识
              "extracted": bool,           # 是否成功提取
              "reason": str (可选)         # 未提取原因
            }
        """
        ...

    @abstractmethod
    def extract_clauses(self, text: str) -> dict[str, Any]:
        """从全文识别关键条款段落

        参数:
          text: 合同全文

        返回:
          条款字典，每个条款结构:
            {
              "extracted": bool,
              "source_text": str | None,
              "position": str | None,
              "matched_keyword": list[str],
              "matched_paragraphs": list[dict]
            }
        """
        ...


class RegexTextExtractor(BaseTextExtractor):
    """基于正则表达式 + 关键词的文本提取器（第二阶段默认实现）

    提取策略:
      - 基本信息: 用正则匹配 "合同编号: XXX" 等 pattern
      - 条款信息: 用关键词定位包含特定词的段落
    """

    # ===== 基本信息提取正则 =====
    PATTERNS = {
        "contract_title": r"^(.+合同|.+协议|.+订单).*$",
        "contract_number": r"合同编号[：:]\s*([^\n]+)",
        # 甲方/乙方: 允许标签与冒号之间存在括号角色说明，如 "甲方（委托方）：..."
        "party_a": r"甲方(?:[（(][^)）]+[)）])?[：:]\s*([^\n]+)",
        "party_b": r"乙方(?:[（(][^)）]+[)）])?[：:]\s*([^\n]+)",
        # 合同金额: 增加 "服务费" 等常见变体标签
        "contract_amount": r"(?:合同金额|总金额|价款|服务费|合同价款|合同总价)[：:]\s*(?:人民币)?\s*([^\n]+)",
        "currency": r"(?:币种|使用货币)[：:]\s*([^\n]+)",
        # 生效日期: 允许日期数字之间存在空格 (如 "2026 年 8 月 1 日")，标签后冒号可选
        # 同时支持 "自 ... 起" 句式，\s* 放在 [日]? 之前确保日字能正确匹配
        "effective_date": (
            r"(?:生效日期|生效时间|开始日期)[：:]?\s*"
            r"(\d{4}\s*[年\-]\s*\d{1,2}\s*[月\-]\s*\d{1,2}\s*[日]?)"
            r"|自\s*(\d{4}\s*[年\-]\s*\d{1,2}\s*[月\-]\s*\d{1,2}\s*[日]?)\s*起"
        ),
        # 到期日期: 允许日期数字之间存在空格，标签后冒号可选
        # 同时支持 "至 ... 止" 句式，\s* 放在 [日]? 之前确保日字能正确匹配
        "expiry_date": (
            r"(?:到期日|有效期至|终止日期|截止日期)[：:]?\s*"
            r"(\d{4}\s*[年\-]\s*\d{1,2}\s*[月\-]\s*\d{1,2}\s*[日]?)"
            r"|至\s*(\d{4}\s*[年\-]\s*\d{1,2}\s*[月\-]\s*\d{1,2}\s*[日]?)\s*止"
        ),
    }

    # ===== 条款关键词 =====
    CLAUSE_KEYWORDS = {
        "payment_clause": ["付款", "支付", "价款", "费用", "预付款"],
        "delivery_clause": ["交付", "交货", "运输", "物流"],
        "acceptance_clause": ["验收", "检验", "测试", "试用"],
        "breach_clause": ["违约", "赔偿", "罚则", "违约金"],
        "confidentiality_clause": ["保密", "机密", "商业秘密"],
        "data_clause": ["数据", "隐私", "个人信息", "数据安全"],
        "ip_clause": ["知识产权", "专利", "商标", "著作权", "版权"],
        "dispute_clause": ["争议", "仲裁", "管辖", "诉讼"],
    }

    def extract_basic_info(self, text: str) -> dict[str, Any]:
        """提取基本信息 — 每个字段独立正则匹配"""
        import re as _re

        result: dict[str, Any] = {}
        for field, pattern in self.PATTERNS.items():
            # 使用 MULTILINE 让 ^ $ 匹配每行
            match = _re.search(pattern, text, _re.MULTILINE)
            if match:
                if match.lastindex:
                    # 多捕获组时取第一个非 None 的组值
                    value = None
                    for i in range(1, match.lastindex + 1):
                        g = match.group(i)
                        if g is not None:
                            value = g.strip()
                            break
                    if value is None:
                        value = match.group(0).strip()
                else:
                    # 无捕获组则取整个匹配
                    value = match.group(0).strip()
                result[field] = {
                    "value": value,
                    "source_text": match.group(0).strip()[:500],
                    "position": "全文匹配",
                    "extracted": True,
                }
            else:
                result[field] = {
                    "value": None,
                    "source_text": None,
                    "position": None,
                    "extracted": False,
                    "reason": f"未匹配到 {field} 对应模式",
                }

        # 币种推断降级: 未直接匹配时从金额字段推断
        if not result.get("currency", {}).get("extracted"):
            amount_src = result.get("contract_amount", {}).get("source_text", "") or ""
            if "人民币" in amount_src or "CNY" in amount_src or "￥" in amount_src or "¥" in amount_src:
                result["currency"] = {
                    "value": "CNY",
                    "source_text": amount_src[:200],
                    "position": "从金额推断",
                    "extracted": True,
                }
            elif "美元" in amount_src or "USD" in amount_src or "$" in amount_src:
                result["currency"] = {
                    "value": "USD",
                    "source_text": amount_src[:200],
                    "position": "从金额推断",
                    "extracted": True,
                }
            elif "欧元" in amount_src or "EUR" in amount_src or "€" in amount_src:
                result["currency"] = {
                    "value": "EUR",
                    "source_text": amount_src[:200],
                    "position": "从金额推断",
                    "extracted": True,
                }

        return result

    def extract_clauses(self, text: str) -> dict[str, Any]:
        """提取条款信息 — 基于关键词定位段落"""

        paragraphs = text.split("\n")
        result: dict[str, Any] = {}

        for clause_name, keywords in self.CLAUSE_KEYWORDS.items():
            matched_paragraphs: list[dict[str, Any]] = []

            for i, para in enumerate(paragraphs):
                if not para.strip():
                    continue
                # 检查段落是否包含任一关键词
                for kw in keywords:
                    if kw in para:
                        matched_paragraphs.append(
                            {
                                "line": i + 1,
                                "text": para.strip()[:500],
                            }
                        )
                        break  # 同一段落不重复添加
                # 限制每个条款最多收集 3 个段落
                if len(matched_paragraphs) >= 3:
                    break

            # 收集命中的关键词（去重，最多 3 个）
            hit_keywords: list[str] = []
            for kw in keywords:
                if any(kw in p["text"] for p in matched_paragraphs):
                    hit_keywords.append(kw)
                if len(hit_keywords) >= 3:
                    break

            result[clause_name] = {
                "extracted": len(matched_paragraphs) > 0,
                "source_text": (
                    matched_paragraphs[0]["text"] if matched_paragraphs else None
                ),
                "position": (
                    f"第{matched_paragraphs[0]['line']}行附近"
                    if matched_paragraphs
                    else None
                ),
                "matched_keyword": hit_keywords,
                "matched_paragraphs": matched_paragraphs,
            }

        return result


def get_extractor() -> BaseTextExtractor:
    """提取器工厂

    根据 settings.EXTRACTOR_TYPE 配置返回对应的提取器:
      - "regex" (默认): 基于正则的提取器（第二阶段）
      - "nlp": 基于 NER 的提取器（第三阶段实现）
    """
    from app.core.config import settings

    ext_type = getattr(settings, "EXTRACTOR_TYPE", "regex")
    if ext_type == "regex":
        return RegexTextExtractor()
    elif ext_type == "nlp":
        # ===== 第三阶段实现 — 已启用 =====
        from app.services.parsers.nlp_extractor import NLPExtractor

        return NLPExtractor()
    raise ValueError(f"未知的提取器类型: {ext_type}")
