"""M04 文档解析器单元测试。"""

import pytest

from app.services.parsers.base import RegexTextExtractor


# ===== 测试用合同全文样本 =====
SAMPLE_CONTRACT = """采购合同
合同编号：XX-2026-001
甲方：甲方科技有限公司
乙方：乙方贸易有限公司
合同金额：人民币壹拾万元整（¥100,000）
币种：CNY
本合同自2026年1月1日起生效，有效期至2026年12月31日。

付款方式：合同签订后7日内支付预付款30%，货到验收后支付60%。
交付时间：卖方应于合同签订后30日内完成交付。
验收标准：按合同附件技术规格书执行。
违约责任：任一方违约应支付合同金额10%的违约金。
保密条款：双方对合同内容负有保密义务。
争议解决：本合同争议提交合同签订地有管辖权的人民法院诉讼解决。
"""

# 缺失部分字段的合同样本
PARTIAL_CONTRACT = """销售协议
合同编号：PARTIAL-001
甲方：测试甲方
"""


class TestRegexTextExtractor:
    """RegexTextExtractor 单元测试"""

    def test_extract_basic_info_all_fields(self):
        """完整合同应提取出所有基本信息字段"""
        extractor = RegexTextExtractor()
        result = extractor.extract_basic_info(SAMPLE_CONTRACT)

        # 应成功提取合同编号
        assert result["contract_number"]["extracted"] is True
        assert "XX-2026-001" in result["contract_number"]["value"]

        # 甲方
        assert result["party_a"]["extracted"] is True
        assert "甲方科技有限公司" in result["party_a"]["value"]

        # 乙方
        assert result["party_b"]["extracted"] is True
        assert "乙方贸易有限公司" in result["party_b"]["value"]

        # 合同金额
        assert result["contract_amount"]["extracted"] is True
        assert "100,000" in result["contract_amount"]["value"] or "100000" in result["contract_amount"]["value"]

        # 生效日期
        assert result["effective_date"]["extracted"] is True
        assert "2026" in result["effective_date"]["value"]

    def test_extract_basic_info_missing_fields(self):
        """缺失字段的合同应标记 extracted=False"""
        extractor = RegexTextExtractor()
        result = extractor.extract_basic_info(PARTIAL_CONTRACT)

        # 已有字段应提取成功
        assert result["contract_number"]["extracted"] is True
        assert result["party_a"]["extracted"] is True

        # 缺失字段应标记为未提取
        assert result["party_b"]["extracted"] is False
        assert "reason" in result["party_b"]

    def test_extract_basic_info_empty_text(self):
        """空文本应全部标记为未提取"""
        extractor = RegexTextExtractor()
        result = extractor.extract_basic_info("")

        for field_info in result.values():
            assert field_info["extracted"] is False

    def test_extract_clauses_full(self):
        """完整合同应识别出多个条款"""
        extractor = RegexTextExtractor()
        result = extractor.extract_clauses(SAMPLE_CONTRACT)

        # 付款条款
        assert result["payment_clause"]["extracted"] is True
        assert result["payment_clause"]["source_text"] is not None

        # 交付条款
        assert result["delivery_clause"]["extracted"] is True

        # 验收条款
        assert result["acceptance_clause"]["extracted"] is True

        # 违约条款
        assert result["breach_clause"]["extracted"] is True

        # 保密条款
        assert result["confidentiality_clause"]["extracted"] is True

        # 争议条款
        assert result["dispute_clause"]["extracted"] is True

    def test_extract_clauses_empty_text(self):
        """空文本应所有条款都标记为未提取"""
        extractor = RegexTextExtractor()
        result = extractor.extract_clauses("")

        for clause_info in result.values():
            assert clause_info["extracted"] is False
            assert clause_info["source_text"] is None

    def test_extract_clauses_matched_keywords(self):
        """命中条款应记录命中的关键词"""
        extractor = RegexTextExtractor()
        result = extractor.extract_clauses(SAMPLE_CONTRACT)

        payment = result["payment_clause"]
        assert payment["extracted"] is True
        assert len(payment["matched_keyword"]) > 0
        # 至少命中了"付款"或"支付"之一
        assert any(kw in {"付款", "支付", "价款"} for kw in payment["matched_keyword"])

    def test_extract_clauses_position_info(self):
        """命中条款应包含位置信息"""
        extractor = RegexTextExtractor()
        result = extractor.extract_clauses(SAMPLE_CONTRACT)

        for clause_name, info in result.items():
            if info["extracted"]:
                assert info["position"] is not None
                assert "行" in info["position"]
