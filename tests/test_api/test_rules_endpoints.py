"""M06 规则审查 API 集成测试。"""

from fastapi.testclient import TestClient


def _seed_rule(client: TestClient) -> int:
    """通过 API 创建测试规则"""
    response = client.post(
        "/api/v1/rules/",
        json={
            "rule_code": "API-R001",
            "rule_name": "API 测试规则",
            "risk_level": "高",
            "match_mode": "keyword",
            "match_text": "违约金,赔偿",
            "suggestion_text": "请检查违约责任。",
        },
    )
    return response.json()["data"]["id"]


def test_list_rules(client: TestClient):
    """GET /rules/ 应返回规则列表"""
    response = client.get("/api/v1/rules/")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)


def test_create_rule(client: TestClient):
    """POST /rules/ 应创建规则"""
    response = client.post(
        "/api/v1/rules/",
        json={
            "rule_code": "API-CREATE-001",
            "rule_name": "创建测试规则",
            "risk_level": "中",
            "match_mode": "keyword",
            "match_text": "测试关键词",
            "suggestion_text": "测试建议",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["rule_code"] == "API-CREATE-001"


def test_create_duplicate_rule_code(client: TestClient):
    """重复 rule_code 应返回错误"""
    client.post(
        "/api/v1/rules/",
        json={
            "rule_code": "DUP-001",
            "rule_name": "第一次",
            "risk_level": "中",
            "match_mode": "keyword",
            "match_text": "kw",
            "suggestion_text": "建议",
        },
    )
    response = client.post(
        "/api/v1/rules/",
        json={
            "rule_code": "DUP-001",
            "rule_name": "第二次",
            "risk_level": "中",
            "match_mode": "keyword",
            "match_text": "kw",
            "suggestion_text": "建议",
        },
    )
    body = response.json()
    assert body["code"] != 0
    assert "已存在" in body["message"]


def test_update_rule(client: TestClient):
    """PUT /rules/{id} 应更新规则"""
    rule_id = _seed_rule(client)
    response = client.put(
        f"/api/v1/rules/{rule_id}",
        json={"rule_name": "更新后的名称"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["rule_name"] == "更新后的名称"


def test_toggle_rule(client: TestClient):
    """PUT /rules/{id}/toggle 应切换规则状态"""
    rule_id = _seed_rule(client)
    response = client.put(f"/api/v1/rules/{rule_id}/toggle?enabled=false")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["rule_status"] == "disabled"


def test_delete_rule(client: TestClient):
    """DELETE /rules/{id} 应删除规则"""
    rule_id = _seed_rule(client)
    response = client.delete(f"/api/v1/rules/{rule_id}")
    assert response.status_code == 200
    assert response.json()["code"] == 0

    # 验证已删除
    get_resp = client.get(f"/api/v1/rules/{rule_id}")
    assert get_resp.json()["code"] != 0


def test_run_rules_no_parse(client: TestClient):
    """POST /rules/run/{task_id} 无解析结果时应返回低风险"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.post(f"/api/v1/rules/run/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    # 无解析结果时应触发阻塞，hits 为空
    assert body["data"]["overall_risk_level"] == "低"
