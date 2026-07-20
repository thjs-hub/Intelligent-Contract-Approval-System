"""合同文档解析 API (M04)。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import ContractParseResponse
from app.services.parse_service import ParseService
from app.utils.response import error_response, success_response

router = APIRouter()


@router.post("/parse/{task_id}")
async def parse_contract_document(
    task_id: int,
    db: Session = Depends(get_db),
):
    """接口: parse_contract_document(document_id)

    触发合同文档解析。会自动选择已下载附件进行解析，
    图片/扫描 PDF 会自动路由到 M05 OCR 模块。
    """
    service = ParseService(db)
    try:
        parse_record = await service.parse_contract_document(task_id)
        data = ContractParseResponse.model_validate(parse_record).model_dump(mode="json")
        return success_response(data=data, message=f"文档解析完成: {parse_record.parse_status}")
    except Exception as e:
        return error_response(f"文档解析失败: {e}")


@router.get("/{task_id}")
def get_parse_result(
    task_id: int,
    db: Session = Depends(get_db),
):
    """查询任务的解析结果"""
    service = ParseService(db)
    parse_record = service.get_parse_result(task_id)
    if not parse_record:
        return error_response(f"任务 {task_id} 暂无解析结果", code=404)
    data = ContractParseResponse.model_validate(parse_record).model_dump(mode="json")
    return success_response(data=data)
