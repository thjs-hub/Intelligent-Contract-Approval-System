"""PDF 合同文档解析器 (M04)。

使用 pdfplumber 读取文本型 PDF，对扫描型 PDF 自动检测并标记为 pending_ocr，
由 M04 ParseService 路由到 M05 OCR 模块处理。
"""

from typing import Any

from app.services.parsers.base import get_extractor


class PDFParser:
    """PDF 合同文档解析器 — 基础版

    解析流程:
      1. 使用 pdfplumber 逐页提取文本
      2. 若文本为空 → 判定为扫描型 PDF，标记 pending_ocr
      3. 调用 RegexTextExtractor 提取基本信息和条款信息
    """

    def parse(self, file_path: str) -> dict[str, Any]:
        """解析 PDF 文件

        参数:
          file_path: PDF 文件绝对路径

        返回:
          {
            "basic_info_json": dict,
            "clause_info_json": dict,
            "is_scanned": bool,  # 是否为扫描型 PDF（无文本层）
          }
        """
        import pdfplumber

        full_text = ""
        page_count = 0

        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    full_text += f"\n=== 第{page.page_number}页 ===\n" + text

        # 检测扫描型 PDF（文本几乎为空）
        is_scanned = len(full_text.strip()) < 50

        if is_scanned:
            # 扫描型 PDF 无文本层，需要 OCR 处理
            return {
                "basic_info_json": {},
                "clause_info_json": {},
                "is_scanned": True,
                "page_count": page_count,
            }

        # 调用通用文本提取器
        extractor = get_extractor()
        basic_info = extractor.extract_basic_info(full_text)
        clause_info = extractor.extract_clauses(full_text)

        return {
            "basic_info_json": basic_info,
            "clause_info_json": clause_info,
            "is_scanned": False,
            "page_count": page_count,
        }

    def extract_text(self, file_path: str) -> str:
        """仅提取 PDF 全文文本"""
        import pdfplumber

        full_text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    full_text += f"\n=== 第{page.page_number}页 ===\n" + text
        return full_text
