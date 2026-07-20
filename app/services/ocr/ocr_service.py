"""OCR 识别服务 (M05)。

对图片类附件和扫描型 PDF 执行光学字符识别，将图像中文字转换为可解析的文本。
被 M04 ParseService 在检测到图片/扫描PDF时自动调用，得到纯文本后继续 M04 字段提取。
"""

from sqlalchemy.orm import Session

from app.services.block_handler import BlockHandler
from app.services.ocr.engine import get_ocr_engine
from app.services.task_log_service import log_error, log_info


class OCRService:
    """OCR 识别服务

    流程:
      1. 根据文件类型选择识别策略（图片/PDF）
      2. 调用 OCR 引擎识别
      3. 识别失败或结果为空 → 触发 M10 阻塞
    """

    def __init__(self, db: Session):
        self.db = db
        # 延迟导入以支持测试时 monkeypatch 引擎工厂
        from app.services.ocr.engine import get_ocr_engine
        self.engine = get_ocr_engine()

    def process_attachment(self, file_path: str, file_type: str, task_id: int) -> str:
        """对附件执行 OCR，返回纯文本

        参数:
          file_path: 文件路径
          file_type: 文件类型 ("image" 或 "pdf")
          task_id: 任务 ID（用于日志记录）

        返回:
          识别出的纯文本

        异常:
          OCR 失败时触发 M10 阻塞并抛出异常
        """
        log_info(self.db, task_id, "M05", f"开始 OCR 识别: {file_path}")

        try:
            if file_type == "pdf":
                # PDF 逐页 OCR
                pages = self.engine.recognize_pdf(file_path)
                full_text = ""
                for page_num, text in pages:
                    full_text += f"\n=== OCR 第{page_num}页 ===\n{text}"
            else:
                # 单张图片 OCR
                full_text = self.engine.recognize(file_path)

            if not full_text.strip():
                raise ValueError("OCR 识别结果为空")

            log_info(
                self.db,
                task_id,
                "M05",
                f"OCR 识别完成，共 {len(full_text)} 字符",
            )
            return full_text

        except Exception as e:
            log_error(self.db, task_id, "M05", f"OCR 识别失败: {e}")
            # ===== M10 触发阻塞 =====
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"OCR 识别失败: {e}", module="M05"
            )
            raise
