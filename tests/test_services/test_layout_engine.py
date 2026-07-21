"""P3-3 OCR 布局分析引擎单元测试。

测试 LayoutOCREngine 和 MockLayoutEngine 的核心功能:
  - MockLayoutEngine 返回结构化布局数据
  - 表格 HTML 解析为单元格二维数组
  - 区域格式化（标题/表格/文本）
  - get_layout_engine 工厂降级行为
"""

import pytest

from app.services.ocr.layout_engine import (
    LayoutOCREngine,
    MockLayoutEngine,
    get_layout_engine,
)


@pytest.fixture
def mock_layout_engine():
    """MockLayoutEngine 实例"""
    return MockLayoutEngine()


class TestMockLayoutEngine:
    """MockLayoutEngine 测试"""

    def test_recognize_with_layout_returns_structure(self, mock_layout_engine):
        """recognize_with_layout 应返回完整结构"""
        result = mock_layout_engine.recognize_with_layout("fake_image.png")
        assert "full_text" in result
        assert "regions" in result
        assert "tables" in result

    def test_recognize_with_layout_full_text_is_string(self, mock_layout_engine):
        """full_text 应为字符串"""
        result = mock_layout_engine.recognize_with_layout("fake_image.png")
        assert isinstance(result["full_text"], str)
        assert len(result["full_text"]) > 0

    def test_recognize_with_layout_regions_have_required_fields(self, mock_layout_engine):
        """每个 region 应包含必要字段"""
        result = mock_layout_engine.recognize_with_layout("fake_image.png")
        for region in result["regions"]:
            assert "type" in region
            assert "text" in region
            assert "bbox" in region
            assert "confidence" in region
            assert region["type"] in [
                "title", "text", "table", "figure", "header", "footer"
            ]

    def test_recognize_with_layout_tables_have_cells(self, mock_layout_engine):
        """表格应包含 cells 二维数组"""
        result = mock_layout_engine.recognize_with_layout("fake_image.png")
        for table in result["tables"]:
            assert "html" in table
            assert "rows" in table
            assert "cols" in table
            assert "cells" in table
            assert isinstance(table["cells"], list)
            assert table["rows"] > 0
            assert table["cols"] > 0

    def test_recognize_table_returns_list(self, mock_layout_engine):
        """recognize_table 应返回表格列表"""
        tables = mock_layout_engine.recognize_table("fake_image.png")
        assert isinstance(tables, list)
        assert len(tables) > 0


class TestLayoutOCREngineParseTable:
    """LayoutOCREngine._parse_table_region 测试（不依赖 PP-Structure）"""

    def test_parse_table_region_extracts_cells(self):
        """_parse_table_region 应从 HTML 提取单元格文本"""
        # 构造 LayoutOCREngine 实例但不初始化引擎（仅测试 _parse_table_region）
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None  # 跳过初始化

        region = {
            "type": "table",
            "res": {
                "html": (
                    "<table><tr><td>项目</td><td>金额</td></tr>"
                    "<tr><td>预付款</td><td>30%</td></tr></table>"
                )
            },
        }
        result = engine._parse_table_region(region)

        assert result["rows"] == 2
        assert result["cols"] == 2
        assert result["cells"] == [["项目", "金额"], ["预付款", "30%"]]

    def test_parse_table_region_empty_html(self):
        """空 HTML 应返回空结构"""
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None

        region = {"type": "table", "res": {"html": ""}}
        result = engine._parse_table_region(region)

        assert result["rows"] == 0
        assert result["cols"] == 0
        assert result["cells"] == []

    def test_parse_table_region_strips_inner_tags(self):
        """应清理单元格内的 HTML 标签"""
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None

        region = {
            "type": "table",
            "res": {
                "html": (
                    "<table><tr>"
                    "<td><b>加粗</b>文本</td>"
                    "<td><span>普通</span></td>"
                    "</tr></table>"
                )
            },
        }
        result = engine._parse_table_region(region)

        assert result["rows"] == 1
        assert result["cols"] == 2
        assert "加粗" in result["cells"][0][0]
        assert "<b>" not in result["cells"][0][0]
        assert "普通" in result["cells"][0][1]


class TestLayoutOCREngineFormatRegion:
    """LayoutOCREngine._format_region 测试"""

    def test_format_title_region(self):
        """标题区域应被 ## 标记"""
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None

        region = {"type": "title", "text": "采购合同"}
        formatted = engine._format_region(region)
        assert "## 采购合同" in formatted

    def test_format_table_region(self):
        """表格区域应被 [表格区域] 标记"""
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None

        region = {"type": "table", "text": "<table>...</table>"}
        formatted = engine._format_region(region)
        assert "[表格区域]" in formatted

    def test_format_text_region(self):
        """文本区域应原样输出"""
        engine = LayoutOCREngine.__new__(LayoutOCREngine)
        engine._table_engine = None

        region = {"type": "text", "text": "普通文本"}
        formatted = engine._format_region(region)
        assert formatted == "普通文本"


class TestGetLayoutEngineFactory:
    """get_layout_engine 工厂测试"""

    def test_get_layout_engine_returns_engine(self):
        """get_layout_engine 应返回引擎实例"""
        engine = get_layout_engine()
        # 应返回 MockLayoutEngine（PP-Structure 依赖未安装时降级）
        assert engine is not None
        # MockLayoutEngine 或 LayoutOCREngine 实例
        assert hasattr(engine, "recognize_with_layout")
        assert hasattr(engine, "recognize_table")

    def test_get_layout_engine_fallback_to_mock(self):
        """PP-Structure 不可用时应降级到 MockLayoutEngine"""
        engine = get_layout_engine()
        # 测试环境无 paddleocr，应返回 MockLayoutEngine
        assert isinstance(engine, MockLayoutEngine)


class TestLayoutOCREngineInitFailure:
    """LayoutOCREngine 初始化失败测试"""

    def test_init_raises_importerror_without_paddleocr(self):
        """无 paddleocr 依赖时初始化应抛 ImportError"""
        with pytest.raises(ImportError, match="PaddleOCR PP-Structure 未安装"):
            LayoutOCREngine()
