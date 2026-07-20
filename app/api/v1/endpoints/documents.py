from fastapi import APIRouter

router = APIRouter()


@router.post("/parse/{document_id}")
def parse_contract_document(document_id: str):
    """解析合同文档并返回结构化字段"""
    return {
        "status": "ok",
        "message": "待实现",
        "data": {"document_id": document_id, "basic_info": {}, "clause_info": {}},
    }
