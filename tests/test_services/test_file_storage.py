"""M02 文件存储服务单元测试。"""

import pytest

from app.services.file_storage import FileStorageService


def test_detect_file_type_docx():
    """DOCX 文件类型检测"""
    assert FileStorageService.detect_file_type("contract.docx") == "docx"
    assert FileStorageService.detect_file_type("contract.DOCX") == "docx"
    assert FileStorageService.detect_file_type("contract.doc") == "docx"


def test_detect_file_type_pdf():
    """PDF 文件类型检测"""
    assert FileStorageService.detect_file_type("agreement.pdf") == "pdf"
    assert FileStorageService.detect_file_type("agreement.PDF") == "pdf"


def test_detect_file_type_image():
    """图片文件类型检测"""
    assert FileStorageService.detect_file_type("scan.png") == "image"
    assert FileStorageService.detect_file_type("scan.jpg") == "image"
    assert FileStorageService.detect_file_type("scan.jpeg") == "image"
    assert FileStorageService.detect_file_type("scan.tiff") == "image"
    assert FileStorageService.detect_file_type("scan.bmp") == "image"


def test_detect_file_type_unknown():
    """未知类型文件检测"""
    assert FileStorageService.detect_file_type("readme.txt") == "unknown"
    assert FileStorageService.detect_file_type("data.csv") == "unknown"
    assert FileStorageService.detect_file_type("noext") == "unknown"


def test_compute_md5():
    """MD5 校验值计算"""
    content1 = b"hello world"
    content2 = b"hello world"
    content3 = b"hello world!"

    md5_1 = FileStorageService.compute_md5(content1)
    md5_2 = FileStorageService.compute_md5(content2)
    md5_3 = FileStorageService.compute_md5(content3)

    # 相同内容应产生相同 MD5
    assert md5_1 == md5_2
    # 不同内容应产生不同 MD5
    assert md5_1 != md5_3
    # MD5 应为 32 位十六进制字符串
    assert len(md5_1) == 32


@pytest.mark.asyncio
async def test_save_file_writes_content(test_upload_dir):
    """save_file 应写入文件内容并返回路径"""
    service = FileStorageService()
    task_id = 10001
    file_name = "test_contract.docx"
    content = b"DOCX file content for testing"

    file_path = await service.save_file(task_id, file_name, content)

    # 文件应存在
    from pathlib import Path

    path = Path(file_path)
    assert path.exists()
    assert path.read_bytes() == content
    # 路径应包含 task_id
    assert str(task_id) in file_path
    assert file_name in file_path


@pytest.mark.asyncio
async def test_save_file_creates_task_dir(test_upload_dir):
    """save_file 应自动创建任务专属目录"""
    service = FileStorageService()
    task_id = 10002

    task_dir = service.get_task_dir(task_id)
    from pathlib import Path

    assert Path(task_dir).exists()
    assert Path(task_dir).is_dir()


@pytest.mark.asyncio
async def test_save_file_path_traversal_protection(test_upload_dir):
    """save_file 应防御路径穿越攻击"""
    service = FileStorageService()
    task_id = 10003
    # 尝试路径穿越
    malicious_name = "../../../etc/passwd"
    content = b"malicious"

    file_path = await service.save_file(task_id, malicious_name, content)

    # 路径应被限制在任务目录内
    from pathlib import Path

    path = Path(file_path)
    assert str(task_id) in file_path
    # 不应访问到 /etc/passwd
    assert "/etc/passwd" not in file_path
