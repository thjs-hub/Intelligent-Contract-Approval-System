"""M05 OCR 服务单元测试。"""

import pytest

from app.models.task import ApprovalTask
from app.services.ocr.engine import MockOCREngine, get_ocr_engine
from app.services.ocr.ocr_service import OCRService


class TestOCREngineFactory:
    """OCR 引擎工厂测试"""

    def test_get_ocr_engine_returns_instance(self):
        """工厂应返回引擎实例"""
        engine = get_ocr_engine()
        assert engine is not None

    def test_mock_engine_recognize(self):
        """MockOCR 引擎应返回非空文本"""
        engine = MockOCREngine()
        text = engine.recognize("/fake/path.png")
        assert text
        assert "合同" in text or "采购" in text

    def test_mock_engine_recognize_pdf(self):
        """MockOCR 引擎 PDF 识别应返回页码列表"""
        engine = MockOCREngine()
        pages = engine.recognize_pdf("/fake/path.pdf")
        assert isinstance(pages, list)
        assert len(pages) >= 1
        # 每条应为 (页码, 文本) 元组
        for page_num, text in pages:
            assert isinstance(page_num, int)
            assert isinstance(text, str)
            assert page_num >= 1


class TestOCRService:
    """OCRService 单元测试"""

    def _create_task(self, db_session) -> ApprovalTask:
        task = ApprovalTask(
            approval_code="OCR-001",
            approval_title="OCR 测试任务",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    def test_process_attachment_image(self, db_session, test_upload_dir):
        """对图片附件执行 OCR 应返回文本"""
        task = self._create_task(db_session)

        # 准备一个假的图片文件（Mock 引擎不读取真实内容）
        from pathlib import Path

        fake_image = Path(test_upload_dir) / "fake.png"
        fake_image.write_bytes(b"fake image content")

        service = OCRService(db_session)
        text = service.process_attachment(
            file_path=str(fake_image),
            file_type="image",
            task_id=task.id,
        )

        assert text  # 非空
        assert "合同" in text or "采购" in text

    def test_process_attachment_pdf(self, db_session, test_upload_dir):
        """对 PDF 附件执行 OCR 应返回文本"""
        task = self._create_task(db_session)

        from pathlib import Path

        fake_pdf = Path(test_upload_dir) / "fake.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        service = OCRService(db_session)
        text = service.process_attachment(
            file_path=str(fake_pdf),
            file_type="pdf",
            task_id=task.id,
        )

        assert text
        assert "OCR 第1页" in text  # MockOCR 引擎返回格式

    def test_process_attachment_failure_triggers_block(
        self, db_session, monkeypatch, test_upload_dir
    ):
        """OCR 失败应触发 M10 阻塞"""
        task = self._create_task(db_session)

        # 模拟 OCR 引擎抛异常 — 直接替换 OCRService 实例的 engine 属性
        class _FailingEngine(MockOCREngine):
            def recognize(self, image_path: str) -> str:
                raise RuntimeError("OCR 引擎故障")

            def recognize_pdf(self, pdf_path: str):
                raise RuntimeError("OCR 引擎故障")

        # 直接 monkeypatch get_ocr_engine 工厂函数
        from app.services.ocr import engine as engine_module

        monkeypatch.setattr(engine_module, "get_ocr_engine", lambda: _FailingEngine())

        # 重新创建 service 以使用 mock 引擎（__init__ 中延迟导入会拿到被 patch 的函数）
        from app.services.ocr.ocr_service import OCRService as _OCRService

        service = _OCRService(db_session)

        with pytest.raises(RuntimeError, match="OCR 引擎故障"):
            service.process_attachment(
                file_path="/fake.png",
                file_type="image",
                task_id=task.id,
            )

        # 任务应被阻塞
        db_session.refresh(task)
        assert task.task_status == "blocked"
