"""审查报告生成服务 — 第三阶段新增（P3-6）。

功能:
  1. AI 摘要生成（LLM 综合审查结果生成摘要，替代模板化摘要）
  2. 风险分布数据生成（供前端可视化图表）
  3. PDF 报告导出（reportlab 生成格式化 PDF）
  4. 优化回写评论生成（含 AI 深度分析风险项）

设计要点:
  - AI 摘要: LLM 不可用时降级到模板摘要
  - PDF 导出: reportlab 不可用时返回错误但不崩溃
  - 中文字体: 优先使用 SimSun，不可用时降级到 Helvetica
  - 回写评论: 同时包含规则命中风险和 AI 识别风险，结构清晰

依赖（可选，未安装时降级）:
  pip install reportlab  # PDF 生成库
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_reviewer import LLMReviewer

logger = logging.getLogger("contract_review")


class ReportService:
    """审查报告生成服务"""

    def __init__(self, db: Session):
        self.db = db

    async def generate_ai_summary(
        self,
        task_id: int,
        rule_hits: list,
        ai_risk_items: list,
        overall_risk_level: str,
    ) -> str:
        """用 LLM 生成审查摘要

        参数:
          task_id: 任务 ID（用于日志）
          rule_hits: 规则命中列表
          ai_risk_items: AI 识别的风险项列表
          overall_risk_level: 总体风险等级

        返回:
          审查摘要文本。LLM 不可用时降级到模板摘要
        """
        reviewer = LLMReviewer()
        return await reviewer.generate_summary(
            rule_hits, ai_risk_items, overall_risk_level
        )

    def generate_risk_distribution(
        self,
        rule_hits: list,
        ai_risk_items: list,
    ) -> dict[str, Any]:
        """生成风险分布数据（供前端可视化图表）

        参数:
          rule_hits: 规则命中列表（RuleHit 对象或字典）
          ai_risk_items: AI 识别的风险项列表（字典）

        返回:
            {
                "by_level": {"高": 3, "中": 5, "低": 2},
                "by_type": {"规则命中": 7, "AI识别": 3},
                "by_category": {"违约责任": 2, "付款条款": 3, ...},
                "total": 10,
            }
        """
        by_level: dict[str, int] = {"高": 0, "中": 0, "低": 0}
        by_category: dict[str, int] = {}

        # 规则命中统计
        for hit in rule_hits:
            rule = self._get_rule_from_hit(hit)
            if rule:
                level = rule.get("risk_level", "中")
                by_level[level] = by_level.get(level, 0) + 1
                category = rule.get("rule_name", "未知规则")
                by_category[category] = by_category.get(category, 0) + 1

        # AI 风险项统计
        for item in ai_risk_items:
            if isinstance(item, dict):
                level = item.get("risk_level", "中")
                by_level[level] = by_level.get(level, 0) + 1
                rtype = item.get("risk_type", "未知")
                by_category[rtype] = by_category.get(rtype, 0) + 1

        total = sum(by_level.values())

        return {
            "by_level": by_level,
            "by_type": {
                "规则命中": len(rule_hits),
                "AI识别": len(ai_risk_items),
            },
            "by_category": by_category,
            "total": total,
        }

    def _get_rule_from_hit(self, hit: Any) -> dict[str, Any] | None:
        """从 RuleHit 对象或字典中提取规则信息"""
        if isinstance(hit, dict):
            return hit
        # RuleHit ORM 对象 — 需查询关联规则
        if hasattr(hit, "rule") and hit.rule:
            return {
                "rule_name": hit.rule.rule_name,
                "risk_level": hit.rule.risk_level,
            }
        # 查询规则
        from app.models.review_rule import ReviewRule

        rule = self.db.get(ReviewRule, getattr(hit, "rule_id", None))
        if rule:
            return {
                "rule_name": rule.rule_name,
                "risk_level": rule.risk_level,
            }
        return None

    def generate_pdf_report(
        self,
        task_id: int,
        review_result: dict[str, Any],
        ai_result: dict[str, Any] | None,
        risk_distribution: dict[str, Any],
    ) -> bytes:
        """生成 PDF 审查报告

        参数:
          task_id: 任务 ID
          review_result: 审查结果（含 overall_risk_level, summary_text, ai_summary, created_at）
          ai_result: AI 审查结果（含 risk_items），无 AI 审查时为 None
          risk_distribution: 风险分布数据

        返回:
          PDF 文件二进制内容

        异常:
          reportlab 未安装时抛 ImportError
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.lib.colors import HexColor
            from reportlab.platypus import (
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError as e:
            raise ImportError(
                "reportlab 未安装，请执行: pip install reportlab"
            ) from e

        import io

        # 注册中文字体（SimSun 优先，不可用降级到 Helvetica）
        font_name = "Helvetica"  # 默认降级字体
        try:
            # Windows 常见中文字体路径
            font_paths = [
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/msyh.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc",
            ]
            for path in font_paths:
                try:
                    pdfmetrics.registerFont(TTFont("ChineseFont", path))
                    font_name = "ChineseFont"
                    break
                except Exception:
                    continue
        except Exception:
            pass

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        # 自定义样式使用注册的中文字体
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=18,
            spaceAfter=20,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            spaceAfter=10,
        )
        body_style = ParagraphStyle(
            "CustomBody",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=16,
        )

        elements: list[Any] = []

        # 标题
        elements.append(Paragraph("智能合同审查报告", title_style))
        elements.append(Spacer(1, 0.5 * cm))

        # 一、基本信息
        elements.append(Paragraph("一、基本信息", heading_style))
        info_data = [
            ["任务编号", str(task_id)],
            ["总体风险等级", review_result.get("overall_risk_level", "未知")],
            ["审查时间", review_result.get("created_at", "")],
        ]
        info_table = Table(info_data, colWidths=[4 * cm, 12 * cm])
        info_table.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (0, -1), HexColor("#f5f5f5")),
            ])
        )
        elements.append(info_table)
        elements.append(Spacer(1, 0.5 * cm))

        # 二、审查摘要
        summary = (
            review_result.get("ai_summary")
            or review_result.get("summary_text", "")
            or "（无摘要）"
        )
        elements.append(Paragraph("二、审查摘要", heading_style))
        elements.append(Paragraph(summary, body_style))
        elements.append(Spacer(1, 0.5 * cm))

        # 三、风险分布
        elements.append(Paragraph("三、风险分布", heading_style))
        by_level = risk_distribution.get("by_level", {})
        dist_data = [
            ["风险等级", "数量"],
            ["高风险", str(by_level.get("高", 0))],
            ["中风险", str(by_level.get("中", 0))],
            ["低风险", str(by_level.get("低", 0))],
            ["合计", str(risk_distribution.get("total", 0))],
        ]
        dist_table = Table(dist_data, colWidths=[4 * cm, 4 * cm])
        dist_table.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e6f7ff")),
            ])
        )
        elements.append(dist_table)
        elements.append(Spacer(1, 0.5 * cm))

        # 四、规则命中详情（简要列表）
        rule_hits = review_result.get("rule_hits", [])
        if rule_hits:
            elements.append(Paragraph("四、规则命中详情", heading_style))
            for i, hit in enumerate(rule_hits[:20], 1):  # 最多展示 20 条
                rule = self._get_rule_from_hit(hit) or {}
                rule_name = rule.get("rule_name", "未知规则")
                risk_level = rule.get("risk_level", "")
                elements.append(
                    Paragraph(
                        f"{i}. 【{risk_level}风险】{rule_name}",
                        body_style,
                    )
                )
            elements.append(Spacer(1, 0.5 * cm))

        # 五、AI 智能审查结果
        if ai_result and ai_result.get("risk_items"):
            elements.append(PageBreak())
            elements.append(Paragraph("五、AI 智能审查结果", heading_style))

            # 总体评估
            assessment = ai_result.get("overall_assessment", "")
            if assessment:
                elements.append(Paragraph("总体评估：", body_style))
                elements.append(Paragraph(assessment, body_style))
                elements.append(Spacer(1, 0.3 * cm))

            # 风险项列表
            for item in ai_result["risk_items"]:
                risk_type = item.get("risk_type", "")
                risk_level = item.get("risk_level", "")
                description = item.get("description", "")
                suggestion = item.get("suggestion", "")
                evidence = item.get("evidence", "")

                elements.append(
                    Paragraph(
                        f"<b>{risk_type}</b> [{risk_level}风险]",
                        body_style,
                    )
                )
                if description:
                    elements.append(Paragraph(f"描述：{description}", body_style))
                if evidence:
                    elements.append(Paragraph(f"原文证据：{evidence}", body_style))
                if suggestion:
                    elements.append(Paragraph(f"建议：{suggestion}", body_style))
                elements.append(Spacer(1, 0.3 * cm))

            # 缺失条款
            missing = ai_result.get("missing_clauses", [])
            if missing:
                elements.append(Spacer(1, 0.3 * cm))
                elements.append(Paragraph("缺失关键条款：", body_style))
                for m in missing:
                    elements.append(Paragraph(f"• {m}", body_style))

        # 报告尾注
        elements.append(Spacer(1, 1 * cm))
        elements.append(
            Paragraph(
                "——本报告由智能合同审查系统自动生成，仅供参考——",
                body_style,
            )
        )

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    def generate_optimized_comment(
        self,
        overall_risk_level: str,
        ai_summary: str,
        rule_hits: list,
        ai_risk_items: list,
        focus_points: list,
    ) -> str:
        """生成优化后的回写评论（AI 摘要 + 结构化风险项）

        相比第二阶段 _generate_comment_text，本方法:
          1. 摘要区域使用 AI 摘要（更精准）
          2. 风险事项分两部分：规则命中风险 + AI 深度分析风险
          3. 新增"缺失关键条款"区块

        参数:
          overall_risk_level: 总体风险等级
          ai_summary: AI 生成的审查摘要（空则用模板摘要）
          rule_hits: 规则命中列表
          ai_risk_items: AI 识别的风险项列表
          focus_points: 审批关注点列表

        返回:
          格式化的回写评论文本
        """
        lines: list[str] = [
            "【智能审查意见】",
            f"总风险等级：{overall_risk_level}",
            "",
        ]

        # AI 摘要（替代模板摘要）
        if ai_summary:
            lines.append(f"审查摘要：{ai_summary}")
        else:
            cnt = len(rule_hits) + len(ai_risk_items)
            lines.append(f"审查摘要：经审查，共发现 {cnt} 项风险点。")

        # 规则命中风险项
        if rule_hits:
            lines.append("")
            lines.append("规则命中风险：")
            for i, hit in enumerate(rule_hits, 1):
                rule = self._get_rule_from_hit(hit)
                if rule:
                    lines.append(
                        f"{i}. 【{rule.get('risk_level', '中')}风险】"
                        f"{rule.get('rule_name', '')}："
                        f"{rule.get('suggestion_text', rule.get('rule_name', ''))}"
                    )

        # AI 识别风险项
        if ai_risk_items:
            lines.append("")
            lines.append("AI 深度分析风险：")
            for i, item in enumerate(ai_risk_items, 1):
                if isinstance(item, dict):
                    lines.append(
                        f"{i}. 【{item.get('risk_level', '中')}风险】"
                        f"{item.get('risk_type', '')}："
                        f"{item.get('suggestion', '')}"
                    )

        # 审批关注点
        if focus_points:
            lines.append("")
            lines.append("审批关注点：")
            for point in focus_points:
                lines.append(f"- {point}")

        # 缺失关键条款（从 AI 风险项中提取）
        if ai_risk_items:
            missing = [
                item.get("risk_type", "")
                for item in ai_risk_items
                if isinstance(item, dict) and "缺失" in item.get("risk_type", "")
            ]
            if missing:
                lines.append("")
                lines.append("缺失关键条款：")
                for m in missing:
                    lines.append(f"- {m}")

        lines.append("")
        lines.append("——以上由智能合同审查系统自动生成，仅供参考——")

        return "\n".join(lines)
