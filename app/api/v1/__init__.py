from fastapi import APIRouter

from app.api.v1.endpoints import (
    approvals,
    attachments,
    comments,
    documents,
    health,
    results,
    rules,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(attachments.router, prefix="/attachments", tags=["attachments"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(results.router, prefix="/results", tags=["results"])
api_router.include_router(comments.router, prefix="/comments", tags=["comments"])
