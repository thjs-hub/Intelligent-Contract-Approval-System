def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"


def test_api_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_approvals_placeholder(client):
    response = client.get("/api/v1/approvals/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rules_placeholder(client):
    response = client.get("/api/v1/rules/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
