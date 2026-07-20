from fastapi import APIRouter

router = APIRouter()


@router.post("/download")
def download_contract_attachment(instance_id: str, attachment_id: str, file_name: str):
    """下载合同附件并返回本地路径"""
    return {
        "status": "ok",
        "message": "待实现",
        "data": {
            "instance_id": instance_id,
            "attachment_id": attachment_id,
            "file_name": file_name,
            "file_path": None,
        },
    }
