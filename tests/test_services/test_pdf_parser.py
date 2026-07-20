"""M04 PDF 解析器与 M04+M05 协作单元测试。"""

import pytest

from app.services.parsers.base import RegexTextExtractor
from app.services.parsers.pdf_parser import PDFParser


class TestPDFParserDetection:
    """PDFParser 类型检测与文本提取测试（不依赖真实 PDF 文件）"""

    def test_pdf_parser_init(self):
        """PDFParser 应可正常实例化"""
        parser = PDFParser()
        assert parser is not None

    def test_extract_text_method_exists(self):
        """extract_text 方法应存在"""
        parser = PDFParser()
        assert hasattr(parser, "extract_text")
        assert hasattr(parser, "parse")


class TestRegexExtractorForOCRText:
    """测试 RegexTextExtractor 对 OCR 输出文本的处理能力"""

    OCR_TEXT = """采购合同
合同编号：OCR-2026-001
甲方：甲方科技有限公司
乙方：乙方贸易有限公司
合同金额：人民币贰拾万元整（¥200,000）
本合同自2026年3月1日起生效。

付款方式：合同签订后7日内支付预付款30%。
交付时间：卖方应于合同签订后30日内完成交付。
违约责任：任一方违约应支付合同金额10%的违约金。
"""

    def test_extract_from_ocr_text(self):
        """从 OCR 输出文本提取字段应正常工作"""
        extractor = RegexTextExtractor()
        basic_info = extractor.extract_basic_info(self.OCR_TEXT)
        clause_info = extractor.extract_clauses(self.OCR_TEXT)

        # 基本信息应提取成功
        assert basic_info["contract_number"]["extracted"] is True
        assert "OCR-2026-001" in basic_info["contract_number"]["value"]
        assert basic_info["party_a"]["extracted"] is True

        # 条款应识别
        assert clause_info["payment_clause"]["extracted"] is True
        assert clause_info["delivery_clause"]["extracted"] is True
        assert clause_info["breach_clause"]["extracted"] is True

    def test_extract_from_low_quality_ocr_text(self):
        """低质量 OCR 文本（含识别错误）应能部分提取"""
        # 模拟 OCR 识别有少量错误
        low_quality_text = """采购台同  # "合" 识别为"台"
合同编号：XX-001
甲方：甲方公司
"""
        extractor = RegexTextExtractor()
        result = extractor.extract_basic_info(low_quality_text)

        # 即使有错误，编号和甲方应能提取
        assert result["contract_number"]["extracted"] is True
        assert result["party_a"]["extracted"] is True
