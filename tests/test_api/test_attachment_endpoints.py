"""M02 合同附件 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient


def _create_task(client: TestClient, code: str = "API-ATT-001") -> int:
    """创建测试任务并返回 task_id"""
    resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    return resp.json()["data"][0]["id"]


def test_download_attachment(client: TestClient):
    """POST /attachments/download 应成功下载附件"""
    task_id = _create_task(client)

    response = client.post(
        "/api/v1/attachments/download",
        json={
            "task_id": task_id,
            "attachment_id": "att-001",
            "file_name": "合同.docx",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["download_status"] == "success"
    assert body["data"]["file_path"]
    assert body["data"]["file_md5"]


def test_list_attachments(client: TestClient):
    """GET /attachments/?task_id=xxx 应返回附件列表"""
    task_id = _create_task(client)
    # 先下载一个附件
    client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-1", "file_name": "f1.docx"},
    )

    response = client.get(f"/api/v1/attachments/?task_id={task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) >= 1


def test_get_attachment(client: TestClient):
    """GET /attachments/{id} 应返回附件详情"""
    task_id = _create_task(client)
    dl_resp = client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-1", "file_name": "f1.docx"},
    )
    attachment_id = dl_resp.json()["data"]["id"]

    response = client.get(f"/api/v1/attachments/{attachment_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] == attachment_id


def test_get_attachment_not_found(client: TestClient):
    """GET /attachments/{id} 不存在的 ID 应返回 404"""
    response = client.get("/api/v1/attachments/99999")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0


def test_download_all_for_task(client: TestClient):
    """POST /attachments/download_all/{task_id} 应批量下载"""
    task_id = _create_task(client)

    response = client.post(f"/api/v1/attachments/download_all/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    # Mock 适配器预置 2 个附件
    assert len(body["data"]) == 2
