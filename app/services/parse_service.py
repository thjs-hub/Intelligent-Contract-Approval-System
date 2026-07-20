"""合同文档解析服务 (M04)。

主入口: parse_contract_document(task_id)
解析流程:
  1. 获取已下载附件，选择第一个可解析文件
  2. 按文件类型选择解析器 (DOCX/PDF/image)
  3. image/扫描PDF → 路由到 M05 OCR
  4. 调用通用文本提取器提取基本信息和条款信息
  5. 失败时触发 M10 阻塞
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attachment import ApprovalAttachment
from app.models.contract_parse import ContractParse
from app.models.task import ApprovalTask
from app.services.block_handler import BlockHandler
from app.services.ocr.ocr_service import OCRService
from app.services.parsers.base import get_extractor
from app.services.parsers.docx_parser import DocxParser
from app.services.parsers.pdf_parser import PDFParser
from app.services.task_log_service import log_error, log_info


class ParseService:
    """合同文档解析服务"""

    def __init__(self, db: Session):
        self.db = db

    async def parse_contract_document(self, task_id: int) -> ContractParse:
        """接口: parse_contract_document(document_id)

        解析合同文档的主入口。

        参数:
          task_id: 任务 ID

        返回:
          ContractParse 对象（含 basic_info_json / clause_info_json）
        """
        # 1. 查找/创建解析记录
        parse_record = self._get_or_create_parse(task_id)

        # 2. 获取已下载附件
        attachments = list(
            self.db.scalars(
                select(ApprovalAttachment)
                .where(
                    ApprovalAttachment.task_id == task_id,
                    ApprovalAttachment.download_status == "success",
                )
                .order_by(ApprovalAttachment.created_at.asc())
            )
        )

        if not attachments:
            parse_record.parse_status = "failed"
            parse_record.parse_error = "无可用附件"
            self.db.commit()
            # ===== M10 触发阻塞 =====
            BlockHandler.trigger_block(
                self.db, task_id, reason="附件缺失，无法解析", module="M04"
            )
            log_error(self.db, task_id, "M04", "无可用附件")
            return parse_record

        # 3. 更新任务状态为 parsing
        task = self.db.scalar(select(ApprovalTask).where(ApprovalTask.id == task_id))
        if task:
            task.task_status = "parsing"
        parse_record.parse_status = "parsing"
        self.db.flush()

        # 4. 按文件类型选择解析器
        attachment = attachments[0]
        file_path = attachment.file_path
        file_type = attachment.file_type or "unknown"

        try:
            if file_type == "docx":
                # DOCX 直接解析
                parser = DocxParser()
                result = parser.parse(file_path)
                self._save_parse_result(parse_record, result)
                log_info(self.db, task_id, "M04", "DOCX 文档解析完成")

            elif file_type == "pdf":
                # PDF 先尝试文本解析，扫描型则路由到 OCR
                parser = PDFParser()
                result = parser.parse(file_path)
                if result.get("is_scanned"):
                    # 扫描型 PDF → 路由到 M05 OCR
                    log_info(
                        self.db,
                        task_id,
                        "M04",
                        "检测到扫描型 PDF，路由至 M05 OCR 模块",
                    )
                    ocr_text = self._call_ocr(task_id, file_path, "pdf")
                    self._extract_from_text(parse_record, ocr_text)
                    log_info(self.db, task_id, "M04", "OCR 后字段提取完成")
                else:
                    self._save_parse_result(parse_record, result)
                    log_info(self.db, task_id, "M04", "PDF 文档解析完成")

            elif file_type == "image":
                # 图片 → 路由到 M05 OCR
                log_info(
                    self.db,
                    task_id,
                    "M04",
                    "图片类附件，路由至 M05 OCR 模块",
                )
                ocr_text = self._call_ocr(task_id, file_path, "image")
                self._extract_from_text(parse_record, ocr_text)
                log_info(self.db, task_id, "M04", "OCR 后字段提取完成")

            else:
                raise ValueError(f"不支持的文件类型: {file_type}")

        except Exception as e:
            parse_record.parse_status = "failed"
            parse_record.parse_error = str(e)[:2000]
            # ===== M10 触发阻塞 =====
            BlockHandler.trigger_block(
                self.db, task_id, reason=f"文档解析失败: {e}", module="M04"
            )
            log_error(self.db, task_id, "M04", f"文档解析失败: {e}")

        self.db.commit()
        return parse_record

    def _get_or_create_parse(self, task_id: int) -> ContractParse:
        """获取或创建解析记录（一对一）"""
        record = self.db.scalar(
            select(ContractParse).where(ContractParse.task_id == task_id)
        )
        if record is None:
            record = ContractParse(task_id=task_id, parse_status="pending")
            self.db.add(record)
            self.db.flush()
        return record

    def _save_parse_result(
        self,
        parse_record: ContractParse,
        result: dict,
    ) -> None:
        """保存解析结果到记录"""
        parse_record.basic_info_json = result.get("basic_info_json", {})
        parse_record.clause_info_json = result.get("clause_info_json", {})
        parse_record.parse_status = "success"
        parse_record.parse_error = None

    def _extract_from_text(
        self,
        parse_record: ContractParse,
        text: str,
    ) -> None:
        """从纯文本提取字段（OCR 完成后复用 M04 的字段提取逻辑）"""
        extractor = get_extractor()
        parse_record.basic_info_json = extractor.extract_basic_info(text)
        parse_record.clause_info_json = extractor.extract_clauses(text)
        parse_record.parse_status = "success"
        parse_record.parse_error = None

    def _call_ocr(self, task_id: int, file_path: str, file_type: str) -> str:
        """调用 M05 OCR 服务"""
        ocr_service = OCRService(self.db)
        return ocr_service.process_attachment(file_path, file_type, task_id)

    def get_parse_result(self, task_id: int) -> Optional[ContractParse]:
        """查询任务的解析结果"""
        return self.db.scalar(
            select(ContractParse).where(ContractParse.task_id == task_id)
        )
