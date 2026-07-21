"""语义匹配引擎 — 第三阶段实现（P3-2）。

基于文本向量（embedding）相似度进行语义级规则匹配。
将规则文本和合同文本分别编码为向量，计算余弦相似度，
超过阈值则判定为语义命中。

相比第二阶段 keyword/regex 模式，semantic 模式能捕捉：
  - 近义表述（"甲方有权终止" ≈ "甲方可单方面解除"）
  - 不平等条款（"甲方有权单方面变更合同内容"）
  - 模糊表述（"按实际情况确定"、"另行协商"）

设计要点:
  - 向量模型延迟加载（避免应用启动慢）
  - 规则向量缓存（同一规则不重复编码）
  - 段落级匹配（避免全文编码丢失局部语义）
  - 依赖未安装时抛 ImportError，由 RuleMatcher 捕获后跳过该规则

依赖（可选，未安装时自动降级）:
  pip install sentence-transformers  # 向量编码模型
  模型: BAAI/bge-small-zh-v1.5 (中文向量模型，约 95MB)
"""

from typing import Any, Optional

from app.core.config import settings


class SemanticMatcher:
    """语义匹配引擎 — 基于向量相似度

    用法:
        matcher = SemanticMatcher()
        score, evidence = matcher.match(
            rule_text="甲方有权单方面变更合同内容",
            search_text=contract_text,
            threshold=0.75,
        )
        if score is not None:
            # 命中
    """

    # 默认相似度阈值（0~1，越高越严格）
    DEFAULT_THRESHOLD = 0.75

    def __init__(self, model_name: str | None = None, threshold: float | None = None):
        """初始化语义匹配器

        参数:
          model_name: HuggingFace 上的中文向量模型名称。None 时从 settings.SEMANTIC_MODEL 读取
          threshold: 相似度阈值。None 时从 settings.SEMANTIC_THRESHOLD 读取
        """
        self._model: Any = None
        self._model_name = model_name or getattr(
            settings, "SEMANTIC_MODEL", "BAAI/bge-small-zh-v1.5"
        )
        self._threshold = float(
            threshold if threshold is not None
            else getattr(settings, "SEMANTIC_THRESHOLD", self.DEFAULT_THRESHOLD)
        )
        # 规则向量缓存: {rule_text: embedding_vector}
        # 用 rule_text 本身作为 key（避免 hash 冲突，规则数量有限）
        self._cache: dict[str, Any] = {}

    def _get_model(self):
        """延迟加载向量模型（首次调用时加载，避免启动慢）

        模型加载失败时抛 ImportError，由调用方（RuleMatcher）捕获后跳过该规则
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers 未安装，请执行: "
                    "pip install sentence-transformers"
                ) from e
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def encode(self, text: str) -> Any:
        """将文本编码为向量

        参数:
          text: 待编码文本

        返回:
          numpy.ndarray 向量（已归一化）
        """
        import numpy as np  # 延迟导入 numpy

        model = self._get_model()
        vec = model.encode(text, normalize_embeddings=True)
        # 确保返回 numpy 数组
        if not isinstance(vec, np.ndarray):
            vec = np.array(vec)
        return vec

    def match(
        self,
        rule_text: str,
        search_text: str,
        threshold: float | None = None,
    ) -> tuple[Optional[float], Optional[str]]:
        """语义匹配

        将合同文本按段落切分，逐段编码并计算与规则文本的余弦相似度，
        取最高相似度段落作为匹配结果。

        参数:
          rule_text: 规则描述文本（如"甲方有权单方面变更合同内容"）
          search_text: 待匹配的合同文本
          threshold: 相似度阈值，None 时用构造时设定的阈值

        返回:
          (similarity_score, evidence_snippet) — 命中时为非 None
          (None, None) — 未命中或输入为空
        """
        if not rule_text or not search_text:
            return None, None

        try:
            import numpy as np
        except ImportError:
            return None, None

        thresh = float(threshold) if threshold is not None else self._threshold

        # 将合同文本按段落切分，逐段匹配（避免全文编码丢失局部语义）
        paragraphs = [
            p.strip() for p in search_text.split("\n") if len(p.strip()) > 10
        ]
        if not paragraphs:
            return None, None

        try:
            model = self._get_model()

            # 批量编码合同段落
            para_embeddings = model.encode(paragraphs, normalize_embeddings=True)
            if not isinstance(para_embeddings, np.ndarray):
                para_embeddings = np.array(para_embeddings)

            # 编码规则文本（带缓存）
            if rule_text not in self._cache:
                rule_emb = model.encode(rule_text, normalize_embeddings=True)
                if not isinstance(rule_emb, np.ndarray):
                    rule_emb = np.array(rule_emb)
                self._cache[rule_text] = rule_emb
            rule_embedding = self._cache[rule_text]

            # 计算每段与规则的余弦相似度（向量已归一化，dot 即 cosine）
            similarities = np.dot(para_embeddings, rule_embedding)

            # 取最高相似度
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])

            if best_score >= thresh:
                evidence = paragraphs[best_idx][:500]
                return best_score, evidence

        except ImportError:
            # 依赖未安装 → 由调用方处理
            raise
        except Exception:
            # 其他异常 → 视为未命中，不抛出（避免影响整体审查流程）
            return None, None

        return None, None

    def batch_match(
        self,
        rule_texts: list[str],
        search_text: str,
        threshold: float | None = None,
    ) -> list[tuple[Optional[float], Optional[str]]]:
        """批量匹配多条规则（复用合同文本编码，提升性能）

        参数:
          rule_texts: 规则文本列表
          search_text: 待匹配的合同文本
          threshold: 相似度阈值

        返回:
          长度与 rule_texts 相同的结果列表
        """
        if not rule_texts:
            return []
        if not search_text:
            return [(None, None)] * len(rule_texts)

        try:
            import numpy as np
        except ImportError:
            return [(None, None)] * len(rule_texts)

        thresh = float(threshold) if threshold is not None else self._threshold

        try:
            model = self._get_model()

            paragraphs = [
                p.strip() for p in search_text.split("\n") if len(p.strip()) > 10
            ]
            if not paragraphs:
                return [(None, None)] * len(rule_texts)

            para_embeddings = model.encode(paragraphs, normalize_embeddings=True)
            if not isinstance(para_embeddings, np.ndarray):
                para_embeddings = np.array(para_embeddings)

            # 编码所有规则文本（带缓存）
            rule_embeddings = []
            for rule_text in rule_texts:
                if rule_text not in self._cache:
                    rule_emb = model.encode(rule_text, normalize_embeddings=True)
                    if not isinstance(rule_emb, np.ndarray):
                        rule_emb = np.array(rule_emb)
                    self._cache[rule_text] = rule_emb
                rule_embeddings.append(self._cache[rule_text])

            # 批量计算相似度
            results: list[tuple[Optional[float], Optional[str]]] = []
            for rule_emb in rule_embeddings:
                similarities = np.dot(para_embeddings, rule_emb)
                best_idx = int(np.argmax(similarities))
                best_score = float(similarities[best_idx])

                if best_score >= thresh:
                    results.append((best_score, paragraphs[best_idx][:500]))
                else:
                    results.append((None, None))
            return results

        except ImportError:
            raise
        except Exception:
            return [(None, None)] * len(rule_texts)

    def clear_cache(self) -> None:
        """清空规则向量缓存（规则更新时调用）"""
        self._cache.clear()
