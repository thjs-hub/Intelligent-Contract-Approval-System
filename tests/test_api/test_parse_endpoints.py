"""M04 文档解析 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient


def _prepare_task_with_attachment(client: TestClient, code: str = "API-PARSE-001") -> int:
    """创建带附件的任务"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]
    client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-1", "file_name": "合同.docx"},
    )
    return task_id


def test_parse_contract_document(client: TestClient):
    """POST /documents/parse/{task_id} 应触发解析"""
    task_id = _prepare_task_with_attachment(client)

    response = client.post(f"/api/v1/documents/parse/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["parse_status"] == "success"
    assert body["data"]["basic_info_json"]


def test_get_parse_result(client: TestClient):
    """GET /documents/{task_id} 应返回解析结果"""
    task_id = _prepare_task_with_attachment(client)
    client.post(f"/api/v1/documents/parse/{task_id}")

    response = client.get(f"/api/v1/documents/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["parse_status"] == "success"


def test_get_parse_result_not_found(client: TestClient):
    """GET /documents/{task_id} 无解析结果应返回 404"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.get(f"/api/v1/documents/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0


def test_parse_no_attachment(client: TestClient):
    """无附件时解析应失败"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.post(f"/api/v1/documents/parse/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["parse_status"] == "failed"
    assert "无可用附件" in body["data"]["parse_error"]
