"""API v1 路由聚合注册。

所有 v1 版本的路由在此聚合后由 main.py 统一挂载到 /api/v1 前缀下。
新增端点时需在此处添加 include_router。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ai_orchestrator,
    ai_review,
    approvals,
    attachments,
    comments,
    documents,
    health,
    logs,
    report,
    results,
    rule_evaluation,
    rules,
)

api_router = APIRouter()

# 健康检查
api_router.include_router(health.router, tags=["health"])

# 业务路由
api_router.include_router(approvals.router, prefix="/approvals", tags=["审批待办"])
api_router.include_router(attachments.router, prefix="/attachments", tags=["合同附件"])
api_router.include_router(documents.router, prefix="/documents", tags=["文档解析"])
api_router.include_router(rules.router, prefix="/rules", tags=["规则审查"])
api_router.include_router(results.router, prefix="/results", tags=["审查结果"])
api_router.include_router(comments.router, prefix="/comments", tags=["评论回写"])

# 管理路由
api_router.include_router(admin.router, prefix="/admin", tags=["系统管理"])
api_router.include_router(logs.router, prefix="/logs", tags=["运行日志"])

# ===== 第三阶段新增路由 — AI 审查能力 =====
api_router.include_router(
    ai_review.router, prefix="/ai-review", tags=["AI 智能审查"]
)
api_router.include_router(
    report.router, prefix="/reports", tags=["审查报告"]
)
api_router.include_router(
    rule_evaluation.router, prefix="/rule-evaluation", tags=["规则评测"]
)
api_router.include_router(
    ai_orchestrator.router, prefix="/orchestrate", tags=["AI 审查编排"]
)
