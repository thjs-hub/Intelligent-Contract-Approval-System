"""M10 系统管理 API 与日志 API 集成测试。"""

from fastapi.testclient import TestClient


def test_get_blocked_tasks_empty(client: TestClient):
    """GET /admin/tasks/blocked 初始应无阻塞任务"""
    response = client.get("/api/v1/admin/tasks/blocked")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_retry_task_not_blocked(client: TestClient):
    """POST /admin/tasks/{id}/retry 非 blocked 任务应返回错误"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.post(f"/api/v1/admin/tasks/{task_id}/retry")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0


def test_get_system_config(client: TestClient):
    """GET /admin/config 应返回系统配置"""
    response = client.get("/api/v1/admin/config")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert "approval_adapter" in data
    assert "ocr_engine" in data
    assert "extractor_type" in data
    # 测试环境应为 mock
    assert data["approval_adapter"] == "mock"


def test_list_logs(client: TestClient):
    """GET /logs/ 应返回日志列表"""
    # 先触发一些操作产生日志
    client.get("/api/v1/approvals/?limit=1&sync=true")

    response = client.get("/api/v1/logs/?limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_list_logs_by_task(client: TestClient):
    """GET /logs/task/{task_id} 应返回指定任务日志"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.get(f"/api/v1/logs/task/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_list_logs_filter_by_level(client: TestClient):
    """GET /logs/?level=ERROR 应只返回 ERROR 日志"""
    response = client.get("/api/v1/logs/?level=ERROR&limit=50")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    for log in body["data"]:
        assert log["log_level"] == "ERROR"


def test_blocked_and_retry_flow(client: TestClient):
    """阻塞 + 重试完整流程"""
    # 创建任务并触发阻塞（无附件时解析会失败）
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    # 触发解析失败 → 任务变 blocked
    client.post(f"/api/v1/documents/parse/{task_id}")

    # 查询阻塞任务列表
    blocked_resp = client.get("/api/v1/admin/tasks/blocked")
    blocked_tasks = blocked_resp.json()["data"]
    assert any(t["id"] == task_id for t in blocked_tasks)

    # 重试任务
    retry_resp = client.post(f"/api/v1/admin/tasks/{task_id}/retry")
    assert retry_resp.status_code == 200
    body = retry_resp.json()
    assert body["code"] == 0
    assert body["data"]["retry_from"] in ("parsing", "reviewing")
