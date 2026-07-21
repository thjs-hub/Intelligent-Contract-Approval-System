"""P3-2 语义匹配引擎单元测试。

测试 SemanticMatcher 的核心功能:
  - match 方法（无 sentence-transformers 依赖时的降级行为）
  - batch_match 批量匹配
  - 缓存机制
  - 异常处理

说明:
  测试环境无 sentence-transformers 依赖，所以测试主要验证:
  1. 依赖缺失时的降级行为（返回 None 而非崩溃）
  2. 空输入处理
  3. 异常捕获不影响主流程
"""

import pytest

from app.services.semantic_matcher import SemanticMatcher


@pytest.fixture
def semantic_matcher():
    """SemanticMatcher 实例"""
    return SemanticMatcher()


class TestSemanticMatcherMatch:
    """match 方法测试"""

    def test_match_empty_rule_text_returns_none(self, semantic_matcher):
        """空规则文本应返回 (None, None)"""
        score, evidence = semantic_matcher.match("", "合同文本")
        assert score is None
        assert evidence is None

    def test_match_empty_search_text_returns_none(self, semantic_matcher):
        """空搜索文本应返回 (None, None)"""
        score, evidence = semantic_matcher.match("规则文本", "")
        assert score is None
        assert evidence is None

    def test_match_short_paragraphs_skipped(self, semantic_matcher):
        """过短段落（≤10 字符）应被跳过"""
        # 段落长度 ≤ 10 应被过滤
        score, evidence = semantic_matcher.match(
            "规则", "短\n短文本\n"
        )
        # 无有效段落时返回 None
        assert score is None
        assert evidence is None

    def test_match_returns_none_when_dependency_missing(self, semantic_matcher):
        """numpy/sentence-transformers 未安装时应静默返回 (None, None)"""
        # 测试环境无 numpy/sentence-transformers
        # match() 应静默返回 (None, None)，不抛异常
        score, evidence = semantic_matcher.match(
            "甲方有权单方面变更合同内容",
            "这是一段足够长的合同文本用于测试语义匹配功能",
        )
        assert score is None
        assert evidence is None

    def test_get_model_raises_importerror_when_dependency_missing(self, semantic_matcher):
        """_get_model 直接调用时应抛 ImportError（由 RuleMatcher 捕获）"""
        # _get_model 不经过 numpy 检查，直接尝试加载 sentence-transformers
        with pytest.raises(ImportError):
            semantic_matcher._get_model()

    def test_match_handles_internal_exception(self, semantic_matcher, monkeypatch):
        """内部异常应被捕获，返回 (None, None)"""
        # 模拟 _get_model 成功但 encode 抛异常
        class MockModel:
            def encode(self, *args, **kwargs):
                raise RuntimeError("encode failed")

        monkeypatch.setattr(semantic_matcher, "_model", MockModel())
        # 此时 _get_model 不会抛 ImportError（model 已设置）
        score, evidence = semantic_matcher.match(
            "甲方有权单方面变更合同内容",
            "这是一段足够长的合同文本用于测试语义匹配功能",
        )
        assert score is None
        assert evidence is None


class TestSemanticMatcherBatchMatch:
    """batch_match 方法测试"""

    def test_batch_match_empty_rules_returns_empty(self, semantic_matcher):
        """空规则列表应返回空列表"""
        results = semantic_matcher.batch_match([], "合同文本")
        assert results == []

    def test_batch_match_empty_search_returns_none_list(self, semantic_matcher):
        """空搜索文本应返回 (None, None) 列表"""
        results = semantic_matcher.batch_match(
            ["规则1", "规则2"], ""
        )
        assert len(results) == 2
        assert all(score is None for score, _ in results)

    def test_batch_match_result_length_matches_rules(self, semantic_matcher):
        """依赖缺失时结果长度应与规则数一致（返回 None 列表）"""
        # 测试环境无 numpy，batch_match 应返回等长的 (None, None) 列表
        rules = ["规则1", "规则2", "规则3"]
        results = semantic_matcher.batch_match(rules, "足够长的合同文本" * 5)
        assert len(results) == 3
        for score, evidence in results:
            assert score is None
            assert evidence is None


class TestSemanticMatcherCache:
    """缓存机制测试"""

    def test_clear_cache(self, semantic_matcher):
        """clear_cache 应清空缓存"""
        # 手动添加一些缓存
        semantic_matcher._cache["test_rule"] = "fake_vector"
        assert len(semantic_matcher._cache) == 1
        semantic_matcher.clear_cache()
        assert len(semantic_matcher._cache) == 0


class TestSemanticMatcherConfig:
    """配置读取测试"""

    def test_threshold_from_config(self, monkeypatch):
        """应从 settings 读取阈值"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_THRESHOLD", 0.85)
        matcher = SemanticMatcher()
        assert matcher._threshold == 0.85

    def test_threshold_override(self):
        """显式传入阈值应覆盖配置"""
        matcher = SemanticMatcher(threshold=0.65)
        assert matcher._threshold == 0.65

    def test_model_name_from_config(self, monkeypatch):
        """应从 settings 读取模型名"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "SEMANTIC_MODEL", "test-model")
        matcher = SemanticMatcher()
        assert matcher._model_name == "test-model"
