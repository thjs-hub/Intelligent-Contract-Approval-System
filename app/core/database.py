"""数据库连接与会话管理。

提供:
  - engine: SQLAlchemy 引擎（懒加载，避免导入时连接数据库）
  - SessionLocal: 会话工厂
  - get_db: FastAPI 依赖注入函数
  - dispose_engine: 应用关闭时释放连接池

设计要点:
  - 引擎懒加载，避免单元测试时强依赖 MySQL
  - 测试环境可通过覆盖 get_db 依赖使用 SQLite 内存数据库
"""

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base

# 模块级变量，懒加载
_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _get_engine():
    """懒加载获取数据库引擎

    首次调用时创建引擎并缓存，避免导入时立即连接数据库。
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
    return _engine


def _get_session_local() -> sessionmaker:
    """懒加载获取会话工厂"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_get_engine()
        )
    return _SessionLocal


# 为了向后兼容，提供 engine 和 SessionLocal 作为属性
# 实际使用时通过 _get_engine() / _get_session_local() 调用


class _EngineProxy:
    """引擎代理 —— 兼容直接访问 engine 的代码"""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)


class _SessionLocalProxy:
    """会话工厂代理"""

    def __call__(self, *args, **kwargs):
        return _get_session_local()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_session_local(), name)


# 向后兼容的导出（实际访问时会触发懒加载）
engine = _EngineProxy()
SessionLocal = _SessionLocalProxy()


def get_db():
    """FastAPI 依赖注入：获取数据库会话

    使用方式:
        @app.get("/")
        def index(db: Session = Depends(get_db)):
            ...
    """
    db = _get_session_local()()
    try:
        yield db
    finally:
        db.close()


def dispose_engine():
    """释放数据库连接池——应在应用关闭时（lifespan shutdown 阶段）调用"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None


def init_engine():
    """主动初始化引擎（应用启动时调用，便于提前发现问题）"""
    _get_engine()
    _get_session_local()
