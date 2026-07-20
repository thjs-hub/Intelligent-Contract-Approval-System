"""ORM 模型公共基类。

所有 ORM 模型继承此类，获得 SQLAlchemy DeclarativeBase 的元数据管理能力。
每个子模型自行定义 id / created_at / updated_at 等公共字段，
便于按需调整字段类型（如 BigInteger 主键、不同的时间戳策略）。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类 —— 仅提供元数据管理，不预设字段"""

    pass
