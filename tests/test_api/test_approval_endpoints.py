"""M01 审批待办 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient


def test_list_approvals_sync(client: TestClient):
    """GET /approvals/ 应返回审批单列表"""
    response = client.get("/api/v1/approvals/?limit=5&sync=true")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 5


def test_list_approvals_without_sync(client: TestClient):
    """GET /approvals/?sync=false 应返回本地任务列表"""
    # 先 sync 一次创建数据
    client.get("/api/v1/approvals/?limit=3&sync=true")

    response = client.get("/api/v1/approvals/?sync=false&limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) >= 3


def test_list_approvals_dedup(client: TestClient):
    """连续两次 sync 同一批数据应去重"""
    r1 = client.get("/api/v1/approvals/?limit=5&sync=true")
    r2 = client.get("/api/v1/approvals/?limit=5&sync=true")

    data1 = r1.json()["data"]
    data2 = r2.json()["data"]

    # 两次返回数量应相同（去重后不重复创建）
    assert len(data1) == len(data2)
    # approval_code 应一致
    codes1 = {item["approval_code"] for item in data1}
    codes2 = {item["approval_code"] for item in data2}
    assert codes1 == codes2


def test_get_approval_by_code(client: TestClient):
    """GET /approvals/{code} 应返回审批单详情"""
    # 先 sync 创建数据
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    code = list_resp.json()["data"][0]["approval_code"]

    response = client.get(f"/api/v1/approvals/{code}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["approval_code"] == code


def test_get_approval_not_found(client: TestClient):
    """GET /approvals/{code} 不存在的 code 应返回 404 错误"""
    response = client.get("/api/v1/approvals/NOT-EXIST-999")
    assert response.status_code == 200  # 业务错误码在 body
    body = response.json()
    assert body["code"] != 0
    assert "不存在" in body["message"]


def test_list_approvals_limit_validation(client: TestClient):
    """limit 参数应被校验"""
    # limit > 100 应返回 422
    response = client.get("/api/v1/approvals/?limit=200")
    assert response.status_code == 422
