"""M07/M08 审查结果与评论回写 API 集成测试。"""

from fastapi.testclient import TestClient


def _prepare_full_pipeline(client: TestClient) -> int:
    """准备完整的任务管道：sync → download → parse → run rules"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    # 下载附件
    client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-1", "file_name": "合同.docx"},
    )
    # 解析
    client.post(f"/api/v1/documents/parse/{task_id}")
    # 执行规则
    client.post(f"/api/v1/rules/run/{task_id}")
    return task_id


def test_save_review_result(client: TestClient):
    """POST /results/save 应保存审查结果"""
    task_id = _prepare_full_pipeline(client)

    response = client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["task_id"] == task_id
    assert body["data"]["comment_text"]  # 回写文本应非空


def test_save_review_result_with_auto_run(client: TestClient):
    """POST /results/save auto_run_rules=true 应自动执行规则"""
    # 准备附件和解析
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]
    client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-1", "file_name": "合同.docx"},
    )
    client.post(f"/api/v1/documents/parse/{task_id}")

    response = client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0


def test_get_review_result(client: TestClient):
    """GET /results/{task_id} 应返回审查结果"""
    task_id = _prepare_full_pipeline(client)
    client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )

    response = client.get(f"/api/v1/results/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["task_id"] == task_id


def test_get_review_result_not_found(client: TestClient):
    """GET /results/{task_id} 无结果应返回 404"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.get(f"/api/v1/results/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0


def test_write_comment(client: TestClient):
    """POST /comments/write/{task_id} 应回写评论"""
    task_id = _prepare_full_pipeline(client)
    client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )

    response = client.post(f"/api/v1/comments/write/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["write_status"] == "success"


def test_write_comment_no_result(client: TestClient):
    """POST /comments/write/{task_id} 无审查结果应返回错误"""
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    response = client.post(f"/api/v1/comments/write/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0
    assert "尚无审查结果" in body["message"]


def test_retry_write_comment(client: TestClient):
    """POST /comments/retry/{task_id} 应重试回写"""
    task_id = _prepare_full_pipeline(client)
    client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )
    client.post(f"/api/v1/comments/write/{task_id}")

    response = client.post(f"/api/v1/comments/retry/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0


def test_get_comment_log(client: TestClient):
    """GET /comments/{task_id} 应返回回写日志"""
    task_id = _prepare_full_pipeline(client)
    client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )
    client.post(f"/api/v1/comments/write/{task_id}")

    response = client.get(f"/api/v1/comments/{task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["write_status"] == "success"
