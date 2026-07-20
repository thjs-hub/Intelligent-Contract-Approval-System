"""测试配置与公共 fixtures。

提供:
  - client: FastAPI TestClient（不需要数据库）
  - db_session: 内存 SQLite 数据库会话（用于服务层单元测试）
  - test_app: 配置好的 FastAPI 应用实例

设计要点:
  - 单元测试使用 SQLite 内存数据库，避免依赖 MySQL
  - 每个测试自动获得干净的数据库（自动建表 + 测试后清理）
  - 通过环境变量强制使用 Mock 适配器和 Mock OCR 引擎
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ===== 测试环境变量覆盖（必须在导入 app 之前设置）=====
os.environ["APPROVAL_ADAPTER"] = "mock"
os.environ["OCR_ENGINE"] = "mock"
os.environ["EXTRACTOR_TYPE"] = "regex"
os.environ["DEBUG"] = "true"
# 测试用临时上传目录
_test_upload_dir = tempfile.mkdtemp(prefix="crs_test_uploads_")
os.environ["UPLOAD_DIR"] = _test_upload_dir

# 导入应用（此时配置已生效）
from app.core.database import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.base import Base  # noqa: E402

# 导入所有模型以触发 Base.metadata 注册
import app.models  # noqa: F401, E402


# ===== SQLite 内存数据库 fixture =====

@pytest.fixture()
def db_engine():
    """创建内存 SQLite 数据库引擎（每个测试独立）"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 创建全部表
    Base.metadata.create_all(engine)
    yield engine
    # 测试结束后销毁
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator:
    """提供数据库会话，测试结束后自动回滚"""
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session) -> TestClient:
    """提供 TestClient，并将 get_db 依赖覆盖为测试会话"""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def test_upload_dir() -> Path:
    """测试用上传目录（自动清理）"""
    yield Path(_test_upload_dir)
    # 测试后清理（仅清空内容，不删除目录本身）
    for child in Path(_test_upload_dir).glob("*"):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            import shutil
            shutil.rmtree(child)
