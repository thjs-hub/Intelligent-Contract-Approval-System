"""业务服务层初始化模块。

提供便捷的别名导出，便于其他模块导入:
  from app.services import block_handlers, log_service
"""

from app.services import block_handler, task_log_service

# 别名: 各模块在异常处理时通过 block_handlers.trigger_block() 调用
block_handlers = block_handler.BlockHandler

# 日志服务别名
log_service = task_log_service

__all__ = ["block_handlers", "log_service", "block_handler", "task_log_service"]
