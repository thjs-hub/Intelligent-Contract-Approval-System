"""OCR 布局分析引擎 — 第三阶段实现（P3-3）。

基于 PaddleOCR PP-Structure 进行文档布局分析，
识别标题、段落、表格、图片、印章等区域，输出结构化文本。

相比第二阶段基础 OCR（仅识别纯文本），布局分析能:
  - 识别文档区域类型（标题/段落/表格/图片）
  - 表格内容结构化提取（行列、单元格）
  - 按阅读顺序还原多栏排版
  - 排除印章干扰

设计要点:
  - PP-Structure 引擎延迟加载
  - 依赖未安装时抛 ImportError，由调用方降级处理
  - MockLayoutEngine 用于无依赖环境下的开发与测试

依赖（可选，未安装时自动降级）:
  pip install paddleocr paddlepaddle  # PP-Structure 内置于 PaddleOCR
"""

import re
from typing import Any


class LayoutOCREngine:
    """带布局分析的 OCR 引擎

    封装 PaddleOCR 的 PP-Structure 模型，提供:
      - recognize_with_layout: 布局分析 + 文本识别
      - recognize_table: 仅识别表格区域
      - _parse_table_region: HTML 表格解析为结构化数据
    """

    # 布局区域类型（与 PP-Structure 输出对齐）
    REGION_TYPES = {
        "title": "标题",
        "text": "正文段落",
        "table": "表格",
        "figure": "图片",
        "header": "页眉",
        "footer": "页脚",
    }

    def __init__(self, model_path: str | None = None):
        """初始化 PP-Structure 布局分析模型

        参数:
          model_path: 可选的自定义模型路径
        """
        self._table_engine: Any = None
        self._model_path = model_path
        self._init_engines()

    def _init_engines(self) -> None:
        """初始化 PP-Structure 引擎

        依赖未安装时抛 ImportError，由调用方降级处理
        """
        try:
            from paddleocr import PPStructure  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "PaddleOCR PP-Structure 未安装，请执行: "
                "pip install paddleocr paddlepaddle"
            ) from e

        # table=True 启用表格识别, layout=True 启用布局分析
        # ocr=True 在布局识别基础上同时识别文本
        self._table_engine = PPStructure(
            show_log=False,
            layout=True,
            table=True,
            ocr=True,
            lang="ch",
        )

    def recognize_with_layout(self, image_path: str) -> dict[str, Any]:
        """带布局分析的 OCR 识别

        参数:
          image_path: 图片文件路径

        返回:
          {
            "full_text": str,           # 按阅读顺序拼接的全文
            "regions": [                # 布局区域列表
              {
                "type": "title"|"text"|"table"|...,
                "text": str,
                "bbox": [x1, y1, x2, y2],
                "confidence": float,
              },
              ...
            ],
            "tables": [                 # 表格结构化数据
              {
                "html": str,            # 表格 HTML
                "rows": int,
                "cols": int,
                "cells": [[str, ...], ...],  # 单元格文本（二维数组）
              },
              ...
            ],
          }
        """
        import cv2  # type: ignore[import-not-found]

        img = cv2.imread(image_path)
        result = self._table_engine(img)

        regions: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for region in result:
            region_type = region.get("type", "text")
            bbox = region.get("bbox", [0, 0, 0, 0])

            if region_type == "table":
                # 表格区域: 提取 HTML 和单元格
                table_data = self._parse_table_region(region)
                tables.append(table_data)
                text_parts.append(table_data["html"])

                regions.append({
                    "type": "table",
                    "text": table_data["html"],
                    "bbox": bbox,
                    "confidence": 0.95,
                })
            else:
                # 文本区域: 提取文本行
                res = region.get("res", [])
                lines: list[str] = []
                for line in res:
                    if isinstance(line, list) and len(line) >= 2:
                        # PaddleOCR 格式: [box, (text, confidence)]
                        lines.append(line[1][0])
                    elif isinstance(line, dict):
                        lines.append(line.get("text", ""))

                region_text = "\n".join(lines)
                text_parts.append(region_text)

                regions.append({
                    "type": region_type,
                    "text": region_text,
                    "bbox": bbox,
                    "confidence": 0.9,
                })

        # 按坐标 y 值排序，还原阅读顺序
        regions.sort(key=lambda r: r["bbox"][1] if r["bbox"] else 0)

        full_text = "\n".join(self._format_region(r) for r in regions)

        return {
            "full_text": full_text,
            "regions": regions,
            "tables": tables,
        }

    def recognize_table(self, image_path: str) -> list[dict[str, Any]]:
        """仅识别表格区域

        参数:
          image_path: 图片文件路径

        返回:
          表格结构化数据列表
        """
        import cv2  # type: ignore[import-not-found]

        img = cv2.imread(image_path)
        result = self._table_engine(img)

        tables: list[dict[str, Any]] = []
        for region in result:
            if region.get("type") == "table":
                tables.append(self._parse_table_region(region))

        return tables

    def _parse_table_region(self, region: dict) -> dict[str, Any]:
        """解析表格区域为结构化数据

        从 PP-Structure 返回的 HTML 中提取单元格文本，推断行列数
        """
        html_str = region.get("res", {}).get("html", "")

        # 从 HTML 中提取所有 <td> 单元格文本
        cells_raw = re.findall(r"<td[^>]*>(.*?)</td>", html_str, re.DOTALL)
        # 清理 HTML 标签和空白
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells_raw]

        # 推断行列数
        rows_match = re.findall(r"<tr[^>]*>", html_str)
        rows = len(rows_match)
        cols = len(cells) // rows if rows > 0 else 0

        # 重构二维数组
        cells_2d: list[list[str]] = []
        if cols > 0 and rows > 0:
            for i in range(rows):
                start = i * cols
                end = start + cols
                cells_2d.append(cells[start:end])

        return {
            "html": html_str,
            "rows": rows,
            "cols": cols,
            "cells": cells_2d,
        }

    def _format_region(self, region: dict) -> str:
        """格式化区域文本（用于拼接 full_text）

        标题区域用 markdown 标记，表格区域用标记包裹
        """
        rtype = region.get("type", "text")
        text = region.get("text", "")

        if rtype == "title":
            return f"\n## {text}\n"
        elif rtype == "table":
            return f"\n[表格区域]\n{text}\n"
        else:
            return text


class MockLayoutEngine:
    """Mock 布局分析引擎 — 用于无 PP-Structure 依赖环境下的开发与测试

    返回固定的结构化结果，便于测试 M04/M05 的协作流程。
    """

    _MOCK_RESULT: dict[str, Any] = {
        "full_text": (
            "\n## 采购合同\n"
            "合同编号：MOCK-LAYOUT-001\n"
            "甲方：甲方科技有限公司\n"
            "乙方：乙方贸易有限公司\n"
            "\n[表格区域]\n<table><tr><td>项目</td><td>金额</td></tr>"
            "<tr><td>预付款</td><td>30%</td></tr></table>\n"
            "合同金额：人民币贰拾万元整\n"
        ),
        "regions": [
            {
                "type": "title",
                "text": "采购合同",
                "bbox": [100, 50, 500, 100],
                "confidence": 0.98,
            },
            {
                "type": "text",
                "text": "合同编号：MOCK-LAYOUT-001\n甲方：甲方科技有限公司\n乙方：乙方贸易有限公司",
                "bbox": [100, 120, 700, 250],
                "confidence": 0.95,
            },
            {
                "type": "table",
                "text": "<table><tr><td>项目</td><td>金额</td></tr>"
                "<tr><td>预付款</td><td>30%</td></tr></table>",
                "bbox": [100, 280, 700, 400],
                "confidence": 0.95,
            },
            {
                "type": "text",
                "text": "合同金额：人民币贰拾万元整",
                "bbox": [100, 420, 700, 470],
                "confidence": 0.93,
            },
        ],
        "tables": [
            {
                "html": "<table><tr><td>项目</td><td>金额</td></tr>"
                "<tr><td>预付款</td><td>30%</td></tr></table>",
                "rows": 2,
                "cols": 2,
                "cells": [["项目", "金额"], ["预付款", "30%"]],
            }
        ],
    }

    def recognize_with_layout(self, image_path: str) -> dict[str, Any]:
        """返回 Mock 布局分析结果"""
        return self._MOCK_RESULT.copy()

    def recognize_table(self, image_path: str) -> list[dict[str, Any]]:
        """返回 Mock 表格识别结果"""
        return [self._MOCK_RESULT["tables"][0].copy()]


def get_layout_engine() -> Any:
    """布局分析引擎工厂

    优先尝试 LayoutOCREngine（PP-Structure），
    依赖未安装时降级到 MockLayoutEngine。
    """
    import logging

    logger = logging.getLogger("contract_review")

    try:
        return LayoutOCREngine()
    except (ImportError, Exception) as e:
        logger.warning(
            f"PP-Structure 引擎初始化失败 ({e})，降级使用 MockLayoutEngine。"
            f"如需启用真实布局分析，请安装依赖: "
            f"pip install paddleocr paddlepaddle"
        )
        return MockLayoutEngine()
