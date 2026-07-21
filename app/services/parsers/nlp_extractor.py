"""NLP 信息抽取提取器 — 第三阶段实现（P3-1）。

基于命名实体识别（NER）模型替换第二阶段的正则提取，提升合同字段抽取的
准确率与覆盖面。实现对合同文本中实体（公司名、金额、日期、地址等）的
语义级识别，并支持条款分类与边界检测。

设计要点:
  - 实现 BaseTextExtractor 接口，与第二阶段 RegexTextExtractor 完全兼容
  - 返回结构必须包含 source_text 字段（M06 规则引擎依赖它构建搜索文本）
  - NER 模型不可用时自动降级到"增强正则"模式（比第二阶段 RegexTextExtractor
    模式更丰富，覆盖更多字段类型）
  - 通过 settings.EXTRACTOR_TYPE=nlp 切换启用，关闭后回退到 RegexTextExtractor

依赖（可选，未安装时自动降级）:
  pip install hanlp        # 中文 NLP 工具包（内置预训练 NER 模型）
  或
  pip install spacy        # 备选 NLP 框架
"""

import re
from typing import Any

from app.services.parsers.base import BaseTextExtractor, RegexTextExtractor


class NLPExtractor(BaseTextExtractor):
    """基于 NER 的合同信息提取器 — 第三阶段实现

    提取策略:
      1. 基本信息: 用 NER 模型识别实体（公司名、金额、日期、编号），
         再用 ENTITY_FIELD_MAP 映射到合同字段
      2. 条款信息: 用 CLAUSE_LABELS 关键词 + 段落语义判断条款类型，
         支持边界检测（最多收集 3 段）
      3. NER 模型不可用时降级到增强正则（_regex_enhanced_extract）
    """

    # NER 实体类型 → 合同字段的映射
    # 不同 NLP 框架的实体标签不同，这里覆盖 HanLP / spaCy 常见标签
    ENTITY_FIELD_MAP: dict[str, list[str]] = {
        # 组织机构名 → 甲乙方（需在上下文中区分甲方/乙方）
        "ORG": ["party_a", "party_b"],
        "ORGANIZATION": ["party_a", "party_b"],
        "COMPANY": ["party_a", "party_b"],
        # 金额 → 合同金额
        "MONEY": ["contract_amount"],
        "MONEY_AMOUNT": ["contract_amount"],
        # 日期 → 生效/到期日期
        "DATE": ["effective_date", "expiry_date"],
        "TIME": ["effective_date", "expiry_date"],
        # 编号类 → 合同编号
        "ID": ["contract_number"],
        "ID_CARD": ["contract_number"],
    }

    # 条款分类标签 — 比第二阶段关键词更丰富的同义词集合
    CLAUSE_LABELS: dict[str, list[str]] = {
        "payment_clause": ["付款方式", "支付条款", "价款与支付", "结算方式", "付款进度"],
        "delivery_clause": ["交付条款", "交货条款", "运输与交付", "交付时间", "交货期"],
        "acceptance_clause": ["验收条款", "检验条款", "验收标准", "质量验收"],
        "breach_clause": ["违约责任", "违约条款", "违约金", "赔偿责任"],
        "confidentiality_clause": ["保密条款", "保密协议", "保密义务", "商业秘密"],
        "data_clause": ["数据保护", "隐私条款", "个人信息", "数据安全"],
        "ip_clause": ["知识产权", "专利条款", "著作权", "技术成果归属"],
        "dispute_clause": ["争议解决", "管辖条款", "仲裁条款", "诉讼管辖"],
    }

    def __init__(self, model_path: str | None = None):
        """初始化 NER 模型

        优先尝试 HanLP（中文 NER 效果最好），失败则降级到增强正则模式。
        模型延迟加载，避免影响应用启动速度。

        参数:
          model_path: 可选的模型路径（用于自定义模型）
        """
        self._ner_model: Any = None
        self._ner_backend: str = "none"  # hanlp / spacy / none
        self._model_path = model_path
        self._init_ner_model(model_path)

    def _init_ner_model(self, model_path: str | None) -> None:
        """加载 NER 模型（失败时静默降级）"""
        # 尝试 HanLP
        try:
            import hanlp  # type: ignore[import-not-found]

            if model_path:
                self._ner_model = hanlp.load(model_path)
            else:
                # 使用 HanLP 预训练中文 NER 模型
                self._ner_model = hanlp.load(hanlp.pretrained.ner.MSRA_NER_BERT_BASE_ZH)
            self._ner_backend = "hanlp"
            return
        except ImportError:
            pass
        except Exception:
            # 模型下载失败等异常 → 降级
            pass

        # 尝试 spaCy
        try:
            import spacy  # type: ignore[import-not-found]

            # 中文模型需用户预装: python -m spacy download zh_core_web_sm
            nlp_name = model_path or "zh_core_web_sm"
            self._ner_model = spacy.load(nlp_name)
            self._ner_backend = "spacy"
            return
        except ImportError:
            pass
        except Exception:
            pass

        # 降级: 无 NER 模型可用，使用增强正则
        self._ner_model = None
        self._ner_backend = "none"

    def extract_basic_info(self, text: str) -> dict[str, Any]:
        """提取基本信息 — NER 实体识别 + 规则后处理

        返回结构与 RegexTextExtractor 完全一致，每个字段:
          {
            "value": str | None,
            "source_text": str | None,
            "position": str | None,
            "extracted": bool,
            "reason": str (可选),
            "confidence": float (可选，仅 NER 模式)
          }
        """
        result: dict[str, Any] = {}

        if self._ner_model is not None:
            # ===== NER 模式 =====
            result = self._extract_with_ner(text)
        else:
            # ===== 降级模式: 增强正则 =====
            result = self._regex_enhanced_extract(text)

        # 补充未提取字段，确保所有字段都有完整结构（与 RegexTextExtractor 行为一致）
        all_fields: set[str] = set()
        for fields in self.ENTITY_FIELD_MAP.values():
            all_fields.update(fields)
        # 加上 RegexTextExtractor 已有的字段（保证字段集兼容）
        all_fields.update(RegexTextExtractor.PATTERNS.keys())

        for field in all_fields:
            if field not in result:
                result[field] = {
                    "value": None,
                    "source_text": None,
                    "position": None,
                    "extracted": False,
                    "reason": f"未识别到 {field} 对应实体",
                }

        # 合同标题: 用规则提取（NER 不擅长标题）
        if not result.get("contract_title", {}).get("extracted"):
            result["contract_title"] = self._extract_title(text)

        # 币种: 从金额上下文推断
        result["currency"] = self._infer_currency(text, result)

        return result

    def extract_clauses(self, text: str) -> dict[str, Any]:
        """提取条款信息 — 文本分类 + 边界检测

        返回结构与 RegexTextExtractor 完全一致，每个条款:
          {
            "extracted": bool,
            "source_text": str | None,
            "position": str | None,
            "matched_keyword": list[str],
            "matched_paragraphs": list[dict]
          }
        """
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        result: dict[str, Any] = {}

        for clause_name, labels in self.CLAUSE_LABELS.items():
            matched_paragraphs: list[dict[str, Any]] = []
            hit_keywords: list[str] = []

            for i, para in enumerate(paragraphs):
                if self._is_clause_paragraph(para, clause_name, labels):
                    matched_paragraphs.append(
                        {
                            "line": i + 1,
                            "text": para[:500],
                        }
                    )
                    # 收集命中的标签（用于 matched_keyword 字段）
                    for label in labels:
                        if label in para and label not in hit_keywords:
                            hit_keywords.append(label)
                        if len(hit_keywords) >= 3:
                            break
                    if len(matched_paragraphs) >= 3:
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

    # ===== NER 提取 =====

    def _extract_with_ner(self, text: str) -> dict[str, Any]:
        """使用 NER 模型提取实体并映射到合同字段"""
        result: dict[str, Any] = {}

        try:
            if self._ner_backend == "hanlp":
                ner_results = self._call_hanlp(text)
            elif self._ner_backend == "spacy":
                ner_results = self._call_spacy(text)
            else:
                return result

            # 用文本中出现的"甲方/乙方/供方/需方"上下文区分甲乙方
            party_a_keywords = ["甲方", "供方", "采购方", "出卖人"]
            party_b_keywords = ["乙方", "需方", "供应方", "买受人"]

            for entity_text, entity_label in ner_results:
                fields = self.ENTITY_FIELD_MAP.get(entity_label, [])
                for field in fields:
                    if field in ("party_a", "party_b"):
                        # 区分甲乙方
                        context = self._find_context(text, entity_text, context_len=30)
                        if field == "party_a" and any(
                            kw in context for kw in party_a_keywords
                        ):
                            self._set_field_if_empty(
                                result, field, entity_text, "NER识别"
                            )
                        elif field == "party_b" and any(
                            kw in context for kw in party_b_keywords
                        ):
                            self._set_field_if_empty(
                                result, field, entity_text, "NER识别"
                            )
                    elif field in ("effective_date", "expiry_date"):
                        # 区分生效/到期日期
                        context = self._find_context(text, entity_text, context_len=20)
                        if field == "effective_date" and any(
                            kw in context for kw in ["生效", "签订", "自"]
                        ):
                            self._set_field_if_empty(
                                result, field, entity_text, "NER识别"
                            )
                        elif field == "expiry_date" and any(
                            kw in context for kw in ["到期", "终止", "有效期至"]
                        ):
                            self._set_field_if_empty(
                                result, field, entity_text, "NER识别"
                            )
                    else:
                        self._set_field_if_empty(
                            result, field, entity_text, "NER识别"
                        )
        except Exception:
            # NER 调用异常 → 降级到增强正则
            return self._regex_enhanced_extract(text)

        return result

    def _call_hanlp(self, text: str) -> list[tuple[str, str]]:
        """调用 HanLP NER 模型，返回 [(实体文本, 标签), ...]"""
        # HanLP 返回格式: {"ner": [["实体文本", "标签"], ...]}
        result = self._ner_model(text)
        if isinstance(result, dict):
            return [(item[0], item[1]) for item in result.get("ner", [])]
        # 兼容其他返回格式
        if isinstance(result, list):
            return [(item[0], item[1]) for item in result if len(item) >= 2]
        return []

    def _call_spacy(self, text: str) -> list[tuple[str, str]]:
        """调用 spaCy NER 模型，返回 [(实体文本, 标签), ...]"""
        doc = self._ner_model(text)
        return [(ent.text, ent.label_) for ent in doc.ents]

    def _set_field_if_empty(
        self,
        result: dict[str, Any],
        field: str,
        value: str,
        position: str,
    ) -> None:
        """仅当字段未提取时设置值（避免被后续实体覆盖）"""
        if not result.get(field, {}).get("extracted"):
            result[field] = {
                "value": value.strip(),
                "source_text": self._find_context(value),
                "position": position,
                "extracted": True,
                "confidence": 0.9,
            }

    # ===== 增强正则（降级模式） =====

    def _regex_enhanced_extract(self, text: str) -> dict[str, Any]:
        """降级模式: 增强版正则提取

        复用 RegexTextExtractor 的提取结果，再用额外的增强模式补充未提取的字段。
        比第二阶段 RegexTextExtractor 模式更丰富，覆盖更多字段类型。
        """
        regex_extractor = RegexTextExtractor()
        basic = regex_extractor.extract_basic_info(text)

        # 增强模式: 覆盖更多合同表述变体
        enhanced_patterns: dict[str, list[str]] = {
            "contract_number": [
                r"合同编号[：:]\s*([^\n]+)",
                r"合同号[：:]\s*([^\n]+)",
                r"编号[：:]\s*([A-Z]{2,}-\d{4}-\d{3,})",  # XX-2026-001 格式
                r"Contract No[.:]\s*([A-Z0-9-]+)",
            ],
            "party_a": [
                # 允许括号内任意角色说明，如 "甲方（委托方）：" / "甲方（卖方）：" 等
                r"甲方(?:[（(][^)）]+[)）])?[：:]\s*([^\n]+)",
                r"供方[：:]\s*([^\n]+)",
                r"采购方[：:]\s*([^\n]+)",
                r"出卖人[：:]\s*([^\n]+)",
            ],
            "party_b": [
                # 允许括号内任意角色说明，如 "乙方（服务方）：" / "乙方（买方）：" 等
                r"乙方(?:[（(][^)）]+[)）])?[：:]\s*([^\n]+)",
                r"需方[：:]\s*([^\n]+)",
                r"供应方[：:]\s*([^\n]+)",
                r"买受人[：:]\s*([^\n]+)",
            ],
            "contract_amount": [
                r"(?:合同总?价|总价款|合同总金额)[：:]\s*(?:人民币)?\s*([^\n]+)",
                r"(?:金额|货款)[（(]含税[)）]?[：:]\s*([^\n]+)",
                r"大写[：:]\s*([^\n]+元[整]?)",
                r"(?:服务费|合同金额|价款)[：:]\s*(?:人民币)?\s*([^\n]+)",
            ],
        }

        for field, patterns in enhanced_patterns.items():
            if not basic.get(field, {}).get("extracted"):
                for pattern in patterns:
                    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
                    if match:
                        basic[field] = {
                            "value": match.group(1).strip(),
                            "source_text": match.group(0).strip()[:500],
                            "position": "增强正则",
                            "extracted": True,
                        }
                        break

        return basic

    # ===== 辅助方法 =====

    def _find_context(
        self, text: str, entity: str = "", context_len: int = 50
    ) -> str:
        """查找实体在原文中的上下文片段"""
        if not entity:
            return text[:context_len * 2]
        idx = text.find(entity)
        if idx == -1:
            return entity
        start = max(0, idx - context_len)
        end = min(len(text), idx + len(entity) + context_len)
        return text[start:end]

    def _extract_title(self, text: str) -> dict[str, Any]:
        """提取合同标题"""
        patterns = [
            r"^(.+合同|.+协议|.+订单).*$",
            r"^【?(.+?)】?\s*$",  # 标题独占一行且被【】包裹
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                return {
                    "value": (
                        match.group(1).strip()
                        if match.lastindex
                        else match.group(0).strip()
                    ),
                    "source_text": match.group(0).strip()[:500],
                    "position": "第1行",
                    "extracted": True,
                }
        return {
            "value": None,
            "source_text": None,
            "position": None,
            "extracted": False,
            "reason": "未识别到合同标题",
        }

    def _infer_currency(self, text: str, basic_info: dict[str, Any]) -> dict[str, Any]:
        """从金额上下文推断币种"""
        amount_info = basic_info.get("contract_amount", {})
        if amount_info.get("source_text"):
            source = amount_info["source_text"]
            if "人民币" in source or "CNY" in source or "￥" in source or "¥" in source:
                return {
                    "value": "CNY",
                    "source_text": source,
                    "position": "推断",
                    "extracted": True,
                }
            if "美元" in source or "USD" in source or "$" in source:
                return {
                    "value": "USD",
                    "source_text": source,
                    "position": "推断",
                    "extracted": True,
                }
            if "欧元" in source or "EUR" in source or "€" in source:
                return {
                    "value": "EUR",
                    "source_text": source,
                    "position": "推断",
                    "extracted": True,
                }
        return {
            "value": None,
            "source_text": None,
            "position": None,
            "extracted": False,
            "reason": "无法推断币种",
        }

    def _is_clause_paragraph(
        self, para: str, clause_name: str, labels: list[str]
    ) -> bool:
        """判断段落是否属于指定条款类型

        优先匹配 CLAUSE_LABELS 中的标签（更具体），
        再降级到 RegexTextExtractor.CLAUSE_KEYWORDS（更宽泛）。
        """
        for label in labels:
            if label in para:
                return True
        # 降级: 用 RegexTextExtractor 的关键词
        keywords = RegexTextExtractor.CLAUSE_KEYWORDS.get(clause_name, [])
        return any(kw in para for kw in keywords)
