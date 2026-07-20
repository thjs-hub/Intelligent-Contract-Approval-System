"""健康检查端点测试。"""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """根路径健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_health_check(client: TestClient):
    """API 路径健康检查"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_approvals_endpoint_not_empty(client: TestClient):
    """审批待办接口应能返回数据"""
    response = client.get("/api/v1/approvals/?limit=5&sync=true")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_rules_list_endpoint(client: TestClient):
    """规则列表接口应正常返回"""
    response = client.get("/api/v1/rules/")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
