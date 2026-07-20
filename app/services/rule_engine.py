"""规则匹配引擎 (M06)。

基础版支持两种匹配模式:
  - keyword: 文本中包含任一关键词即命中
  - regex: 文本匹配任一正则即命中
  - semantic: 第三阶段扩展点，第二阶段跳过

每条规则匹配成功后返回 (evidence_text, evidence_position)，
用于创建 RuleHit 记录和生成审批关注点。
"""

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit


class RuleMatcher:
    """规则匹配引擎 — 基础版（keyword + regex）"""

    # 关键词匹配时返回的证据上下文长度（前后各 50 字符）
    _EVIDENCE_CONTEXT_LEN = 50

    def __init__(self, db: Session):
        self.db = db

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
            evidence, position = self._match_rule(rule, search_text)

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
            # 注意: 基础版不记录 miss，第三阶段可扩展

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
          - semantic 模式: 第三阶段扩展点，第二阶段跳过
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
            # ===== 第三阶段扩展点 =====
            # 第二阶段暂不支持语义匹配，跳过
            # TODO: 第三阶段实现 SemanticMatcher 后启用
            return None, None
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
