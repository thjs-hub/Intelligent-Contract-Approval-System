"""OCR 服务包初始化。"""

from app.services.ocr.engine import (
    MockOCREngine,
    OCREngine,
    PaddleOCREngine,
    TesseractEngine,
    get_ocr_engine,
)

__all__ = [
    "OCREngine",
    "PaddleOCREngine",
    "TesseractEngine",
    "MockOCREngine",
    "get_ocr_engine",
]
