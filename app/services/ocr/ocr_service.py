"""OCR 识别服务 (M05)。

对图片类附件和扫描型 PDF 执行光学字符识别，将图像中文字转换为可解析的文本。
被 M04 ParseService 在检测到图片/扫描PDF时自动调用，得到纯文本后继续 M04 字段提取。

第三阶段增强 (P3-3):
  - process_attachment_with_layout: 带布局分析的 OCR 识别
    识别标题/段落/表格区域，输出结构化文本，供 M04 更精确地提取字段
  - 通过 settings.OCR_USE_LAYOUT 配置开关控制是否启用
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.block_handler import BlockHandler
from app.services.task_log_service import log_error, log_info

logger = logging.getLogger("contract_review")


class OCRService:
    """OCR 识别服务

    流程:
      1. 根据文件类型选择识别策略（图片/PDF）
      2. 调用 OCR 引擎识别
      3. 识别失败或结果为空 → 触发 M10 阻塞

    第三阶段增强:
      - process_attachment_with_layout: 布局分析 OCR，输出结构化文本
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

    # ===== 第三阶段实现 — 布局分析 OCR =====
    def process_attachment_with_layout(
        self, file_path: str, file_type: str, task_id: int
    ) -> dict[str, Any]:
        """带布局分析的 OCR 识别（第三阶段新增）

        返回结构化文本（含布局标记 + 表格结构），供 M04 更精确地提取字段。

        参数:
          file_path: 文件路径
          file_type: 文件类型 ("image" 或 "pdf")
          task_id: 任务 ID

        返回:
          {
            "full_text": str,           # 按阅读顺序拼接的结构化文本
            "regions": [...],           # 布局区域列表
            "tables": [...],            # 表格结构化数据
          }

        异常:
          布局分析失败时触发 M10 阻塞并抛出异常
        """
        log_info(self.db, task_id, "M05", f"开始布局分析OCR: {file_path}")

        try:
            if file_type == "pdf":
                # PDF: 逐页布局分析
                import fitz  # type: ignore[import-not-found]

                doc = fitz.open(file_path)
                all_regions: list[dict[str, Any]] = []
                all_tables: list[dict[str, Any]] = []
                full_text_parts: list[str] = []

                for page_num in range(len(doc)):
                    page = doc[page_num]
                    pix = page.get_pixmap(dpi=300)
                    img_path = f"/tmp/ocr_layout_page_{page_num}.png"
                    pix.save(img_path)

                    result = self.engine.recognize_with_layout(img_path)
                    all_regions.extend(result["regions"])
                    all_tables.extend(result["tables"])
                    full_text_parts.append(
                        f"\n=== 第{page_num + 1}页 ===\n{result['full_text']}"
                    )

                full_text = "\n".join(full_text_parts)
                log_info(
                    self.db,
                    task_id,
                    "M05",
                    f"PDF 布局分析完成: {len(all_regions)}个区域, "
                    f"{len(all_tables)}个表格",
                )
                return {
                    "full_text": full_text,
                    "regions": all_regions,
                    "tables": all_tables,
                }
            else:
                # 单张图片
                result = self.engine.recognize_with_layout(file_path)
                log_info(
                    self.db,
                    task_id,
                    "M05",
                    f"布局分析完成: {len(result.get('regions', []))}个区域, "
                    f"{len(result.get('tables', []))}个表格",
                )
                return result

        except Exception as e:
            log_error(self.db, task_id, "M05", f"布局分析OCR失败: {e}")
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"布局分析OCR失败: {e}", module="M05"
            )
            raise
