"""规则效果评测服务 — 第三阶段新增（P3-5）。

对每条规则统计命中率、误报率，生成评测报告，
为规则调优提供数据支撑。

评测维度:
  - 命中次数 (hit_count): 规则在所有审查任务中命中的总次数
  - 命中率 (hit_rate): hit_count / total_tasks
  - 规则状态 (status):
      - "active": 正常工作（命中率在合理范围）
      - "never_hit": 从未命中（可能规则过严或不适用）
      - "too_broad": 命中率过高（>0.8，可能误报多）
      - "low_hit": 命中率过低（<0.05，可能规则不适用）

设计要点:
  - 仅依赖已有 rule_hits 表数据，不需要额外标注数据
  - 评测结果用于前端规则管理页展示和调优建议
  - 支持单条规则详情查询（含最近命中证据）
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.review_rule import ReviewRule
from app.models.rule_hit import RuleHit
from app.models.task import ApprovalTask


class RuleEvaluator:
    """规则效果评测器"""

    # 状态判定阈值
    TOO_BROAD_THRESHOLD = 0.8  # 命中率 > 0.8 视为过宽（可能误报多）
    LOW_HIT_THRESHOLD = 0.05   # 命中率 < 0.05 视为命中过低

    def __init__(self, db: Session):
        self.db = db

    def evaluate_all(self) -> list[dict[str, Any]]:
        """评测所有规则的效果

        返回:
            [
                {
                    "rule_id": int,
                    "rule_code": str,
                    "rule_name": str,
                    "match_mode": str,
                    "risk_level": str,
                    "rule_status": str,
                    "total_tasks": int,       # 已审查的合同总数（非 pending 状态）
                    "hit_count": int,         # 命中次数
                    "hit_rate": float,        # 命中率 = hit_count / total_tasks
                    "status": "active"|"never_hit"|"too_broad"|"low_hit",
                },
                ...
            ]
        """
        # 1. 统计每条规则的命中次数
        hit_counts = self.db.execute(
            select(
                RuleHit.rule_id,
                func.count(RuleHit.id).label("hit_count"),
            )
            .where(RuleHit.hit_status == "hit")
            .group_by(RuleHit.rule_id)
        ).all()
        hit_map = {row.rule_id: row.hit_count for row in hit_counts}

        # 2. 获取所有规则
        rules = list(self.db.scalars(select(ReviewRule)))

        # 3. 统计已审查的合同总数（task_status != 'pending'，即已经进入过审查流程的任务）
        # 这样无命中的任务也会计入分母，使命中率更准确
        total_tasks = self.db.scalar(
            select(func.count(ApprovalTask.id)).where(
                ApprovalTask.task_status != "pending"
            )
        ) or 0

        # 4. 计算每条规则的评测数据
        results: list[dict[str, Any]] = []
        for rule in rules:
            hit_count = hit_map.get(rule.id, 0)
            hit_rate = (hit_count / total_tasks) if total_tasks > 0 else 0.0

            # 规则状态判定
            if hit_count == 0:
                status = "never_hit"
            elif hit_rate > self.TOO_BROAD_THRESHOLD:
                status = "too_broad"
            elif hit_rate < self.LOW_HIT_THRESHOLD:
                status = "low_hit"
            else:
                status = "active"

            results.append({
                "rule_id": rule.id,
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "match_mode": rule.match_mode,
                "risk_level": rule.risk_level,
                "rule_status": rule.rule_status,
                "total_tasks": total_tasks,
                "hit_count": hit_count,
                "hit_rate": round(hit_rate, 4),
                "status": status,
            })

        return results

    def get_rule_detail(self, rule_id: int) -> dict[str, Any]:
        """获取单条规则的详细评测数据（含最近命中证据）

        参数:
          rule_id: 规则 ID

        返回:
          {
            "rule": {rule_code, rule_name, match_mode, match_text, risk_level, ...},
            "recent_hits": [
              {task_id, evidence_text, evidence_position, created_at},
              ...
            ]
          }
          规则不存在时返回空字典
        """
        rule = self.db.scalar(select(ReviewRule).where(ReviewRule.id == rule_id))
        if not rule:
            return {}

        # 查询最近 20 条命中记录
        recent_hits = list(
            self.db.scalars(
                select(RuleHit)
                .where(
                    RuleHit.rule_id == rule_id,
                    RuleHit.hit_status == "hit",
                )
                .order_by(RuleHit.created_at.desc())
                .limit(20)
            )
        )

        return {
            "rule": {
                "rule_id": rule.id,
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "match_mode": rule.match_mode,
                "match_text": rule.match_text,
                "risk_level": rule.risk_level,
                "rule_status": rule.rule_status,
                "suggestion_text": rule.suggestion_text,
            },
            "recent_hits": [
                {
                    "task_id": h.task_id,
                    "evidence_text": (h.evidence_text or "")[:200],
                    "evidence_position": h.evidence_position,
                    "created_at": h.created_at.isoformat() if h.created_at else "",
                }
                for h in recent_hits
            ],
            "hit_count": len(recent_hits),
        }

    def get_evaluation_summary(self) -> dict[str, Any]:
        """获取规则评测汇总数据（用于前端仪表盘展示）

        返回:
          {
            "total_rules": int,
            "active_rules": int,
            "never_hit_rules": int,
            "too_broad_rules": int,
            "low_hit_rules": int,
            "total_tasks": int,
            "total_hits": int,
            "avg_hit_rate": float,
          }
        """
        all_results = self.evaluate_all()
        total_rules = len(all_results)
        total_tasks = all_results[0]["total_tasks"] if all_results else 0
        total_hits = sum(r["hit_count"] for r in all_results)
        avg_hit_rate = (
            sum(r["hit_rate"] for r in all_results) / total_rules
            if total_rules > 0
            else 0.0
        )

        status_counts = {
            "active": 0,
            "never_hit": 0,
            "too_broad": 0,
            "low_hit": 0,
        }
        for r in all_results:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

        return {
            "total_rules": total_rules,
            "active_rules": status_counts["active"],
            "never_hit_rules": status_counts["never_hit"],
            "too_broad_rules": status_counts["too_broad"],
            "low_hit_rules": status_counts["low_hit"],
            "total_tasks": total_tasks,
            "total_hits": total_hits,
            "avg_hit_rate": round(avg_hit_rate, 4),
        }
