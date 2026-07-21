"""OCR 引擎抽象层 (M05)。

定义统一的 OCR 引擎接口，第二阶段支持 PaddleOCR 和 Tesseract 两种实现。
通过 settings.OCR_ENGINE 配置切换引擎。
"""

from abc import ABC, abstractmethod
from typing import Tuple


class OCREngine(ABC):
    """OCR 引擎抽象基类

    第三阶段扩展点:
      - recognize_with_layout: 带布局分析的识别（识别段落/标题/表格区域）
      - recognize_table: 表格识别
    """

    @abstractmethod
    def recognize(self, image_path: str) -> str:
        """对单张图片执行 OCR

        参数:
          image_path: 图片文件路径

        返回:
          识别出的文本（多行用 \\n 分隔）
        """
        ...

    @abstractmethod
    def recognize_pdf(self, pdf_path: str) -> list[Tuple[int, str]]:
        """对 PDF 逐页 OCR

        参数:
          pdf_path: PDF 文件路径

        返回:
          [(页码, 文本), ...] 列表，页码从 1 开始
        """
        ...

    # ===== 第三阶段扩展点 =====
    def recognize_with_layout(self, image_path: str) -> dict:
        """带布局分析的识别（识别段落、标题、表格区域）

        第三阶段实现。
        """
        raise NotImplementedError("第三阶段实现: 带布局分析的 OCR")

    def recognize_table(self, image_path: str) -> list:
        """表格识别

        第三阶段实现。
        """
        raise NotImplementedError("第三阶段实现: 表格识别")


class PaddleOCREngine(OCREngine):
    """基于 PaddleOCR 的识别引擎（推荐首选，准确率较高）

    依赖:
      pip install paddleocr paddlepaddle

    第三阶段增强: 通过组合 LayoutOCREngine 提供布局分析能力
    """

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR

            # use_angle_cls=True 启用方向分类，lang="ch" 中文识别
            self.ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        except ImportError as e:
            raise ImportError(
                "PaddleOCR 未安装，请执行: pip install paddleocr paddlepaddle"
            ) from e
        # 第三阶段: 布局分析引擎延迟初始化（首次调用 recognize_with_layout 时加载）
        self._layout_engine = None

    def recognize(self, image_path: str) -> str:
        """对单张图片执行 OCR"""
        result = self.ocr.ocr(image_path, cls=True)
        if not result or not result[0]:
            return ""
        # PaddleOCR 返回格式: [[box, (text, confidence)], ...]
        lines = [line[1][0] for line in result[0]]
        return "\n".join(lines)

    def recognize_pdf(self, pdf_path: str) -> list[Tuple[int, str]]:
        """对 PDF 逐页 OCR — 先转图片再识别"""
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        results: list[Tuple[int, str]] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            # dpi=300 保证清晰度
            pix = page.get_pixmap(dpi=300)
            img_path = f"/tmp/ocr_page_{page_num}.png"
            pix.save(img_path)
            text = self.recognize(img_path)
            results.append((page_num + 1, text))
        return results

    # ===== 第三阶段实现 — 布局分析 =====
    def recognize_with_layout(self, image_path: str) -> dict:
        """带布局分析的识别（识别段落、标题、表格区域）

        通过组合 LayoutOCREngine 实现，PP-Structure 不可用时降级到 MockLayoutEngine
        """
        if self._layout_engine is None:
            from app.services.ocr.layout_engine import get_layout_engine

            self._layout_engine = get_layout_engine()
        return self._layout_engine.recognize_with_layout(image_path)

    def recognize_table(self, image_path: str) -> list:
        """表格识别"""
        if self._layout_engine is None:
            from app.services.ocr.layout_engine import get_layout_engine

            self._layout_engine = get_layout_engine()
        return self._layout_engine.recognize_table(image_path)


class TesseractEngine(OCREngine):
    """基于 Tesseract 的识别引擎（备选方案）

    依赖:
      1. 安装 Tesseract OCR 引擎（系统级）
      2. pip install pytesseract Pillow
    """

    def __init__(self) -> None:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "Tesseract 依赖未安装，请执行: pip install pytesseract Pillow"
            ) from e

    def recognize(self, image_path: str) -> str:
        """对单张图片执行 OCR"""
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        # chi_sim+eng 中英文混合识别
        return pytesseract.image_to_string(img, lang="chi_sim+eng")

    def recognize_pdf(self, pdf_path: str) -> list[Tuple[int, str]]:
        """对 PDF 逐页 OCR"""
        import fitz

        doc = fitz.open(pdf_path)
        results: list[Tuple[int, str]] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img_path = f"/tmp/ocr_page_{page_num}.png"
            pix.save(img_path)
            text = self.recognize(img_path)
            results.append((page_num + 1, text))
        return results


class MockOCREngine(OCREngine):
    """Mock OCR 引擎 — 用于无 OCR 依赖环境下的开发调试

    返回一段固定的合同文本，便于测试 M04 与 M05 的协作流程。

    第三阶段增强: 实现 recognize_with_layout / recognize_table，
    返回固定的结构化结果，便于测试 P3-3 布局分析功能。
    """

    _MOCK_TEXT = """采购合同
合同编号：MOCK-OCR-001
甲方：甲方科技有限公司
乙方：乙方贸易有限公司
合同金额：人民币贰拾万元整（¥200,000）
本合同自2026年3月1日起生效。

付款方式：合同签订后7日内支付预付款30%。
交付时间：卖方应于合同签订后30日内完成交付。
验收标准：按合同附件技术规格书执行。
违约责任：任一方违约应支付合同金额10%的违约金。
保密条款：双方对合同内容负有保密义务。
争议解决：本合同争议提交合同签订地有管辖权的人民法院诉讼解决。
"""

    def recognize(self, image_path: str) -> str:
        return self._MOCK_TEXT

    def recognize_pdf(self, pdf_path: str) -> list[Tuple[int, str]]:
        return [(1, self._MOCK_TEXT)]

    # ===== 第三阶段实现 — Mock 布局分析 =====
    def recognize_with_layout(self, image_path: str) -> dict:
        """返回 Mock 布局分析结果

        复用 MockLayoutEngine 的结构化输出，便于测试 P3-3 流程
        """
        from app.services.ocr.layout_engine import MockLayoutEngine

        return MockLayoutEngine().recognize_with_layout(image_path)

    def recognize_table(self, image_path: str) -> list:
        """返回 Mock 表格识别结果"""
        from app.services.ocr.layout_engine import MockLayoutEngine

        return MockLayoutEngine().recognize_table(image_path)


def get_ocr_engine() -> OCREngine:
    """OCR 引擎工厂

    根据 settings.OCR_ENGINE 配置返回对应的引擎:
      - "paddle" (默认): PaddleOCR 引擎
      - "tesseract": Tesseract 引擎
      - "mock": Mock 引擎（开发调试用）

    若目标引擎依赖未安装，自动降级到 MockOCREngine 并打印警告。
    """
    from app.core.config import settings
    import logging

    logger = logging.getLogger("contract_review")
    engine_type = getattr(settings, "OCR_ENGINE", "paddle")

    if engine_type == "mock":
        return MockOCREngine()

    if engine_type == "paddle":
        try:
            return PaddleOCREngine()
        except (ImportError, Exception) as e:
            logger.warning(
                f"PaddleOCR 引擎初始化失败 ({e})，降级使用 MockOCREngine。"
                f"如需启用真实 OCR，请安装依赖: pip install paddleocr paddlepaddle"
            )
            return MockOCREngine()

    if engine_type == "tesseract":
        try:
            return TesseractEngine()
        except (ImportError, Exception) as e:
            logger.warning(
                f"Tesseract 引擎初始化失败 ({e})，降级使用 MockOCREngine。"
                f"如需启用真实 OCR，请安装 Tesseract 和 pip install pytesseract Pillow"
            )
            return MockOCREngine()

    raise ValueError(f"未知的 OCR 引擎类型: {engine_type}")
