"""任务运行日志服务 (M09)。

为所有业务模块提供统一的日志记录接口:
  - log_info / log_warn / log_error: 写入数据库 task_logs 表 + Python 标准日志
  - get_task_logs: 按任务 ID 查询历史日志

设计要点:
  - 数据库日志写入失败不抛异常，避免阻断业务流程
  - 不在此处 commit，由调用方的事务统一提交
  - 同时输出到 Python logging 模块，便于文件日志收集
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task_log import TaskLog

# 模块级 logger，日志同时输出到控制台和文件
module_logger = logging.getLogger("contract_review")


def log_info(db: Session, task_id: Optional[int], module: str, content: str) -> None:
    """记录 INFO 级别日志

    参数:
      db: 数据库会话
      task_id: 关联任务 ID（系统级日志可为 None）
      module: 模块标识，如 "M01" / "M02"
      content: 日志内容
    """
    module_logger.info(f"[{module}] task={task_id} | {content}")
    _write_db_log(db, task_id, "INFO", module, content)


def log_warn(db: Session, task_id: Optional[int], module: str, content: str) -> None:
    """记录 WARN 级别日志"""
    module_logger.warning(f"[{module}] task={task_id} | {content}")
    _write_db_log(db, task_id, "WARN", module, content)


def log_error(db: Session, task_id: Optional[int], module: str, content: str) -> None:
    """记录 ERROR 级别日志"""
    module_logger.error(f"[{module}] task={task_id} | {content}")
    _write_db_log(db, task_id, "ERROR", module, content)


def _write_db_log(
    db: Session,
    task_id: Optional[int],
    level: str,
    log_type: str,
    content: str,
) -> None:
    """写入数据库日志（内部方法）

    日志写入失败时仅记录到 Python logger，不抛异常，
    避免日志故障影响主业务流程。
    """
    try:
        log_entry = TaskLog(
            task_id=task_id,
            log_level=level,
            log_type=log_type,
            # 截断超长内容，避免单条日志过大
            log_content=content[:5000] if content else None,
        )
        db.add(log_entry)
        # 立即 flush 使日志对后续查询可见（不 commit，由调用方事务统一提交）
        db.flush()
        # 注意: 不在此处 commit，由调用方的事务统一提交
    except Exception:
        # 日志写入失败不应阻断业务流程
        module_logger.exception("日志写入数据库失败")


def get_task_logs(
    db: Session,
    task_id: int,
    limit: int = 100,
    level: Optional[str] = None,
    log_type: Optional[str] = None,
) -> list[TaskLog]:
    """查询某任务的日志列表

    参数:
      db: 数据库会话
      task_id: 任务 ID
      limit: 返回条数上限，默认 100
      level: 可选日志级别过滤 (INFO / WARN / ERROR)
      log_type: 可选模块过滤 (M01 / M02 ...)

    返回:
      按时间倒序排列的 TaskLog 列表
    """
    stmt = (
        select(TaskLog)
        .where(TaskLog.task_id == task_id)
        .order_by(TaskLog.created_at.desc())
        .limit(limit)
    )
    if level:
        stmt = stmt.where(TaskLog.log_level == level)
    if log_type:
        stmt = stmt.where(TaskLog.log_type == log_type)
    return list(db.scalars(stmt))


def get_all_logs(
    db: Session,
    limit: int = 100,
    level: Optional[str] = None,
    log_type: Optional[str] = None,
    task_id: Optional[int] = None,
) -> list[TaskLog]:
    """查询全系统日志（供管理页使用）

    参数同 get_task_logs，但 task_id 可选
    """
    stmt = select(TaskLog).order_by(TaskLog.created_at.desc()).limit(limit)
    if task_id is not None:
        stmt = stmt.where(TaskLog.task_id == task_id)
    if level:
        stmt = stmt.where(TaskLog.log_level == level)
    if log_type:
        stmt = stmt.where(TaskLog.log_type == log_type)
    return list(db.scalars(stmt))
