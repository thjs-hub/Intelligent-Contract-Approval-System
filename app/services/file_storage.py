"""本地文件存储服务 (M02)。

负责附件的本地文件系统存储管理:
  - 按任务 ID 创建专属目录
  - 异步写入文件
  - 文件 MD5 校验值计算
  - 文件类型检测（决定路由到 M04 还是 M05）

第三阶段扩展点: 可替换为 MinioStorageService 或 OSSStorageService。
"""

import hashlib
from pathlib import Path

import aiofiles

from app.core.config import settings


class FileStorageService:
    """本地文件存储服务

    所有附件按 task_id 分目录存储在 settings.UPLOAD_DIR 下。
    目录结构示例: uploads/{task_id}/{file_name}
    """

    # 文件扩展名 → 业务类型映射
    _TYPE_MAP = {
        ".docx": "docx",
        ".doc": "docx",
        ".pdf": "pdf",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".bmp": "image",
        ".gif": "image",
    }

    def __init__(self) -> None:
        # 初始化基础存储目录
        self.base_dir = Path(settings.UPLOAD_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_task_dir(self, task_id: int) -> Path:
        """获取任务专属附件目录

        参数:
          task_id: 任务 ID

        返回:
          任务专属目录 Path，目录会自动创建
        """
        task_dir = self.base_dir / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    async def save_file(self, task_id: int, file_name: str, content: bytes) -> str:
        """保存文件并返回绝对路径

        参数:
          task_id: 任务 ID（用于分目录存储）
          file_name: 文件名
          content: 文件二进制内容

        返回:
          文件绝对路径字符串
        """
        # 安全校验: 防止 file_name 包含路径穿越字符
        safe_name = Path(file_name).name
        file_path = self.get_task_dir(task_id) / safe_name
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        return str(file_path.absolute())

    @staticmethod
    def compute_md5(content: bytes) -> str:
        """计算文件 MD5 校验值

        参数:
          content: 文件二进制内容

        返回:
          32 位十六进制 MD5 字符串
        """
        return hashlib.md5(content).hexdigest()

    @classmethod
    def detect_file_type(cls, file_name: str) -> str:
        """根据文件扩展名检测业务文件类型

        参数:
          file_name: 文件名

        返回:
          业务类型: "docx" / "pdf" / "image" / "unknown"
          决定 M04 解析器路由: docx/pdf → M04 文档解析；image → M05 OCR
        """
        ext = Path(file_name).suffix.lower()
        return cls._TYPE_MAP.get(ext, "unknown")
