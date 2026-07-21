"""P3-1 NLP 信息抽取器单元测试。

测试 NLPExtractor 的核心功能:
  - 增强正则降级模式（无 NER 依赖时的默认行为）
  - 基本信息提取（合同标题/编号/甲乙方/金额/日期/币种）
  - 条款信息提取（8 类条款分类与边界检测）
  - 工厂切换（EXTRACTOR_TYPE=nlp 时返回 NLPExtractor）
  - 与第二阶段 RegexTextExtractor 的字段结构兼容性
"""

import pytest

from app.services.parsers.base import BaseTextExtractor, RegexTextExtractor, get_extractor
from app.services.parsers.nlp_extractor import NLPExtractor


# ===== 测试用合同文本 =====

CONTRACT_TEXT = """采购合同
合同编号：TEST-2026-001
甲方（卖方）：甲方科技有限公司
乙方（买方）：乙方贸易有限公司
合同金额：人民币贰拾万元整（¥200,000）
本合同自2026年3月1日起生效，至2027年2月28日到期。

付款方式：合同签订后7日内支付预付款30%，验收合格后支付尾款70%。
交付时间：卖方应于合同签订后30日内完成交付。
验收标准：按合同附件技术规格书执行。
违约责任：任一方违约应支付合同金额10%的违约金。
保密条款：双方对合同内容负有保密义务。
数据保护：双方应遵守数据安全相关法律法规。
知识产权：合同执行过程中产生的技术成果归属甲方所有。
争议解决：本合同争议提交合同签订地有管辖权的人民法院诉讼解决。
"""


@pytest.fixture
def nlp_extractor():
    """NLPExtractor 实例（无 NER 依赖，使用增强正则降级模式）"""
    return NLPExtractor()


class TestNLPExtractorBasic:
    """基本信息提取测试"""

    def test_extract_basic_info_returns_all_fields(self, nlp_extractor):
        """应返回所有字段（含未提取的字段）"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        assert isinstance(result, dict)
        # 应包含 RegexTextExtractor 的所有字段
        for field in RegexTextExtractor.PATTERNS.keys():
            assert field in result, f"字段 {field} 应在结果中"
            assert "extracted" in result[field]
            assert "source_text" in result[field]
            assert "position" in result[field]

    def test_extract_contract_title(self, nlp_extractor):
        """应正确提取合同标题"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        title_info = result["contract_title"]
        assert title_info["extracted"] is True
        assert "合同" in title_info["value"] or "协议" in title_info["value"]

    def test_extract_contract_number(self, nlp_extractor):
        """应正确提取合同编号"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        number_info = result["contract_number"]
        assert number_info["extracted"] is True
        assert "TEST-2026-001" in number_info["value"]

    def test_extract_party_a_with_parentheses(self, nlp_extractor):
        """应正确提取甲方（含"（卖方）"括号说明）"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        party_a = result["party_a"]
        assert party_a["extracted"] is True
        assert "甲方科技" in party_a["value"]

    def test_extract_party_b_with_parentheses(self, nlp_extractor):
        """应正确提取乙方（含"（买方）"括号说明）"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        party_b = result["party_b"]
        assert party_b["extracted"] is True
        assert "乙方贸易" in party_b["value"]

    def test_extract_contract_amount(self, nlp_extractor):
        """应正确提取合同金额"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        amount = result["contract_amount"]
        assert amount["extracted"] is True

    def test_infer_currency_cny(self, nlp_extractor):
        """应从金额上下文推断币种为 CNY"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        currency = result["currency"]
        assert currency["extracted"] is True
        assert currency["value"] == "CNY"

    def test_extracted_field_has_source_text(self, nlp_extractor):
        """已提取的字段必须包含 source_text（M06 规则引擎依赖此字段）"""
        result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        for field, info in result.items():
            if info.get("extracted"):
                assert info.get("source_text") is not None, (
                    f"字段 {field} 已提取但 source_text 为空"
                )


class TestNLPExtractorClauses:
    """条款信息提取测试"""

    def test_extract_clauses_returns_all_clause_types(self, nlp_extractor):
        """应返回 8 类条款"""
        result = nlp_extractor.extract_clauses(CONTRACT_TEXT)
        assert isinstance(result, dict)
        expected_clauses = {
            "payment_clause",
            "delivery_clause",
            "acceptance_clause",
            "breach_clause",
            "confidentiality_clause",
            "data_clause",
            "ip_clause",
            "dispute_clause",
        }
        assert expected_clauses.issubset(set(result.keys()))

    def test_extract_payment_clause(self, nlp_extractor):
        """应识别付款条款"""
        result = nlp_extractor.extract_clauses(CONTRACT_TEXT)
        payment = result["payment_clause"]
        assert payment["extracted"] is True
        assert payment["source_text"] is not None
        assert len(payment["matched_paragraphs"]) > 0

    def test_extract_breach_clause(self, nlp_extractor):
        """应识别违约责任条款"""
        result = nlp_extractor.extract_clauses(CONTRACT_TEXT)
        breach = result["breach_clause"]
        assert breach["extracted"] is True
        assert "违约" in breach["source_text"]

    def test_clause_structure_compatible_with_regex_extractor(self, nlp_extractor):
        """条款结构应与 RegexTextExtractor 兼容"""
        result = nlp_extractor.extract_clauses(CONTRACT_TEXT)
        for clause_name, info in result.items():
            assert "extracted" in info
            assert "source_text" in info
            assert "position" in info
            assert "matched_keyword" in info
            assert "matched_paragraphs" in info
            assert isinstance(info["matched_keyword"], list)
            assert isinstance(info["matched_paragraphs"], list)

    def test_clause_max_three_paragraphs(self, nlp_extractor):
        """每类条款最多收集 3 个段落"""
        # 构造含 5 个付款段落的文本
        text = "合同\n" + "付款条款：内容\n" * 5
        result = nlp_extractor.extract_clauses(text)
        assert len(result["payment_clause"]["matched_paragraphs"]) <= 3


class TestNLPExtractorFactory:
    """工厂切换测试"""

    def test_get_extractor_returns_nlp_when_configured(self, monkeypatch):
        """EXTRACTOR_TYPE=nlp 时应返回 NLPExtractor"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "EXTRACTOR_TYPE", "nlp")
        extractor = get_extractor()
        assert isinstance(extractor, NLPExtractor)
        assert isinstance(extractor, BaseTextExtractor)

    def test_get_extractor_returns_regex_by_default(self, monkeypatch):
        """默认应返回 RegexTextExtractor"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "EXTRACTOR_TYPE", "regex")
        extractor = get_extractor()
        assert isinstance(extractor, RegexTextExtractor)

    def test_get_extractor_unknown_type_raises(self, monkeypatch):
        """未知类型应抛 ValueError"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "EXTRACTOR_TYPE", "unknown")
        with pytest.raises(ValueError, match="未知的提取器类型"):
            get_extractor()


class TestNLPExtractorFallback:
    """降级模式测试"""

    def test_nlp_extractor_without_ner_uses_enhanced_regex(self, nlp_extractor):
        """无 NER 依赖时应使用增强正则降级模式"""
        # NLPExtractor 初始化时 NER 模型加载失败，应降级
        assert nlp_extractor._ner_model is None
        assert nlp_extractor._ner_backend == "none"

    def test_enhanced_regex_extracts_more_patterns(self, nlp_extractor):
        """增强正则应识别 RegexTextExtractor 无法识别的模式"""
        # "供方"前缀 — RegexTextExtractor 默认 PATTERNS 不包含
        text = """供应合同
合同编号：ENHANCED-001
供方：供方公司
需方：需方公司
"""
        result = nlp_extractor.extract_basic_info(text)
        # 增强正则应能识别"供方"
        party_a = result["party_a"]
        assert party_a["extracted"] is True
        assert "供方公司" in party_a["value"]

    def test_nlp_extractor_compatible_with_regex_extractor_fields(self, nlp_extractor):
        """NLPExtractor 输出应与 RegexTextExtractor 字段集兼容"""
        nlp_result = nlp_extractor.extract_basic_info(CONTRACT_TEXT)
        regex_extractor = RegexTextExtractor()
        regex_result = regex_extractor.extract_basic_info(CONTRACT_TEXT)

        # 两者字段集应一致
        assert set(nlp_result.keys()) == set(regex_result.keys())


class TestNLPExtractorInferCurrency:
    """币种推断测试"""

    def test_infer_currency_usd(self, nlp_extractor):
        """应从金额上下文推断 USD"""
        text = """购销合同
合同金额：100,000 USD
"""
        result = nlp_extractor.extract_basic_info(text)
        assert result["currency"]["extracted"] is True
        assert result["currency"]["value"] == "USD"

    def test_infer_currency_none_when_no_amount(self, nlp_extractor):
        """无金额信息时应无法推断币种"""
        text = "这是一段不含金额的文本。"
        result = nlp_extractor.extract_basic_info(text)
        assert result["currency"]["extracted"] is False
