"""规则匹配引擎 (M06)。

基础版支持两种匹配模式:
  - keyword: 文本中包含任一关键词即命中
  - regex: 文本匹配任一正则即命中
  - semantic: 第三阶段实现，基于向量相似度的语义匹配

每条规则匹配成功后返回 (evidence_text, evidence_position)，
用于创建 RuleHit 记录和生成审批关注点。
"""

import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit

logger = logging.getLogger("contract_review")


class RuleMatcher:
    """规则匹配引擎 — 支持 keyword / regex / semantic 三种模式"""

    # 关键词匹配时返回的证据上下文长度（前后各 50 字符）
    _EVIDENCE_CONTEXT_LEN = 50

    def __init__(self, db: Session):
        self.db = db
        # 语义匹配器延迟初始化（避免无 sentence-transformers 依赖时启动报错）
        self._semantic_matcher = None
        # 检查语义匹配总开关
        from app.core.config import settings

        self._semantic_enabled = getattr(settings, "SEMANTIC_ENABLED", False)

    def _get_semantic_matcher(self):
        """延迟获取语义匹配器

        首次调用时实例化 SemanticMatcher。
        若 sentence-transformers 未安装，抛 ImportError 由调用方捕获。
        """
        if self._semantic_matcher is None:
            from app.services.semantic_matcher import SemanticMatcher

            self._semantic_matcher = SemanticMatcher()
        return self._semantic_matcher

    def match_all(
        self,
        task_id: int,
        basic_info: dict,
        clause_info: dict,
    ) -> tuple[list[RuleHit], list[str]]:
        """执行所有启用规则的匹配

        参数:
          task_id: 任务 ID
          basic_info: M04 提取的基本信息 JSON
          clause_info: M04 提取的条款信息 JSON

        返回:
          (命中规则列表, 审批关注点列表)
          - 命中规则列表: RuleHit 对象列表（已 db.add 但未 commit）
          - 审批关注点列表: 高风险规则命中的建议文本
        """
        # 1. 加载所有启用规则
        rules = list(
            self.db.scalars(
                select(ReviewRule).where(ReviewRule.rule_status == "enabled")
            )
        )

        # 2. 构建可搜索文本：拼接所有 source_text
        search_text = self._build_search_text(basic_info, clause_info)

        # 3. 逐条匹配
        hits: list[RuleHit] = []
        focus_points: list[str] = []

        for rule in rules:
            evidence, position = self._match_rule(
                rule, search_text, basic_info, clause_info
            )

            if evidence:
                # 命中 → 创建 RuleHit
                hit = RuleHit(
                    task_id=task_id,
                    rule_id=rule.id,
                    evidence_text=evidence[:2000],
                    evidence_position=position,
                    hit_status="hit",
                )
                self.db.add(hit)
                hits.append(hit)

                # 高风险 → 加入审批关注点
                if rule.risk_level == "高":
                    focus_points.append(
                        f"【高风险】{rule.rule_name}：{rule.suggestion_text}"
                    )

        self.db.flush()
        return hits, focus_points

    def _match_rule(
        self,
        rule: ReviewRule,
        search_text: str,
        basic_info: dict | None = None,
        clause_info: dict | None = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """单条规则匹配

        返回:
          (evidence_text, evidence_position) — 命中时为非 None
          未命中时均为 None

        说明:
          - keyword 模式: match_text 按逗号分隔为多个关键词，任一命中即匹配
          - regex 模式: match_text 作为单个正则表达式处理（不按逗号分隔，
            因为正则中 {2,3} 等语法自身包含逗号）
          - semantic 模式: 第三阶段实现，基于向量相似度匹配
        """
        if not rule.match_text:
            return None, None

        if rule.match_mode == "keyword":
            # keyword 模式: 按逗号分隔多个关键词
            patterns = [p.strip() for p in rule.match_text.split(",") if p.strip()]
            return self._keyword_match(patterns, search_text)
        elif rule.match_mode == "regex":
            # regex 模式: 整个 match_text 作为单个正则表达式
            return self._regex_match([rule.match_text], search_text)
        elif rule.match_mode == "semantic":
            # ===== 第三阶段实现 — 语义匹配 =====
            return self._semantic_match(rule, search_text)
        return None, None

    def _semantic_match(
        self, rule: ReviewRule, search_text: str
    ) -> tuple[Optional[str], Optional[str]]:
        """语义匹配 — 基于 SemanticMatcher 向量相似度

        保护策略:
          - SEMANTIC_ENABLED=False 时直接跳过（不影响其他规则）
          - sentence-transformers 未安装时跳过并记录警告
          - 匹配过程异常时跳过（不影响整体审查流程）
        """
        # 总开关关闭 → 跳过
        if not self._semantic_enabled:
            return None, None

        # search_text 为空时跳过
        if not search_text or not search_text.strip():
            return None, None

        try:
            matcher = self._get_semantic_matcher()
            # semantic 规则的 match_text 可能是逗号分隔的多个语义描述
            # 任一描述命中即视为规则命中
            descriptions = [
                p.strip() for p in rule.match_text.split(",") if p.strip()
            ]
            if not descriptions:
                return None, None

            best_score: Optional[float] = None
            best_evidence: Optional[str] = None

            for desc in descriptions:
                score, evidence = matcher.match(desc, search_text)
                if score is not None and (
                    best_score is None or score > best_score
                ):
                    best_score = score
                    best_evidence = evidence

            if best_score is not None and best_evidence:
                return best_evidence, f"语义匹配: 相似度={best_score:.2f}"

        except ImportError:
            # sentence-transformers 未安装 → 跳过该规则，记录一次警告
            logger.warning(
                f"语义匹配规则 {rule.rule_code} 跳过: "
                f"sentence-transformers 未安装"
            )
        except Exception as e:
            # 其他异常 → 跳过，不影响其他规则
            logger.warning(
                f"语义匹配规则 {rule.rule_code} 执行异常: {e}"
            )

        return None, None

    def _keyword_match(
        self,
        keywords: list[str],
        text: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """关键词匹配 — 文本中包含任一关键词即命中

        返回证据为关键词前后各 50 字符的上下文。
        """
        for kw in keywords:
            if not kw:
                continue
            idx = text.find(kw)
            if idx != -1:
                # 返回关键词前后 50 字作为证据
                start = max(0, idx - self._EVIDENCE_CONTEXT_LEN)
                end = min(len(text), idx + len(kw) + self._EVIDENCE_CONTEXT_LEN)
                evidence = text[start:end]
                return evidence, f"关键词匹配: {kw}"
        return None, None

    def _regex_match(
        self,
        patterns: list[str],
        text: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """正则匹配 — 文本匹配任一正则即命中"""
        for pattern in patterns:
            if not pattern:
                continue
            try:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    evidence = match.group(0)[:500]
                    return evidence, f"正则匹配: {pattern}"
            except re.error:
                # 正则语法错误时跳过该 pattern
                continue
        return None, None

    def _build_search_text(self, basic_info: dict, clause_info: dict) -> str:
        """构建可搜索文本 — 拼接所有解析字段的 source_text

        保证规则匹配能命中所有解析出的原文片段。
        """
        parts: list[str] = []
        for field, info in (basic_info or {}).items():
            if isinstance(info, dict) and info.get("source_text"):
                parts.append(info["source_text"])
        for clause, info in (clause_info or {}).items():
            if isinstance(info, dict) and info.get("source_text"):
                parts.append(info["source_text"])
        return "\n".join(parts)
