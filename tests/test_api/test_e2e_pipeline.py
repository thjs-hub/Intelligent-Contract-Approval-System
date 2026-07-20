"""端到端闭环集成测试。

模拟完整用户旅程: 审批拉取 → 附件下载 → 文档解析 → 规则审查 → 结果保存 → 评论回写
"""

import pytest
from fastapi.testclient import TestClient


def test_full_pipeline_happy_path(client: TestClient):
    """完整闭环 Happy Path 测试"""
    # Step 1: 拉取审批单
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    assert list_resp.status_code == 200
    task_id = list_resp.json()["data"][0]["id"]
    assert task_id is not None

    # Step 2: 下载附件
    dl_resp = client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-001", "file_name": "合同.docx"},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.json()["data"]["download_status"] == "success"

    # Step 3: 解析文档
    parse_resp = client.post(f"/api/v1/documents/parse/{task_id}")
    assert parse_resp.status_code == 200
    assert parse_resp.json()["data"]["parse_status"] == "success"
    # 验证基本信息已提取
    basic_info = parse_resp.json()["data"]["basic_info_json"]
    assert basic_info  # 非空

    # Step 4: 执行规则审查
    rules_resp = client.post(f"/api/v1/rules/run/{task_id}")
    assert rules_resp.status_code == 200
    rules_data = rules_resp.json()["data"]
    assert "overall_risk_level" in rules_data
    assert "summary_text" in rules_data
    assert isinstance(rules_data["hits"], list)

    # Step 5: 保存审查结果
    save_resp = client.post(
        "/api/v1/results/save",
        json={"task_id": task_id, "auto_run_rules": False},
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()["data"]
    assert save_data["comment_text"]  # 回写文本已生成
    assert save_data["overall_risk_level"] in ("低", "中", "高")

    # Step 6: 回写评论
    write_resp = client.post(f"/api/v1/comments/write/{task_id}")
    assert write_resp.status_code == 200
    write_data = write_resp.json()["data"]
    assert write_data["write_status"] == "success"

    # 验证任务最终状态
    detail_resp = client.get(
        f"/api/v1/approvals/{list_resp.json()['data'][0]['approval_code']}"
    )
    task = detail_resp.json()["data"]
    assert task["task_status"] == "done"
    assert task["write_status"] == "success"


def test_full_pipeline_with_logs(client: TestClient):
    """完整流程后应能查询到所有模块的日志"""
    # 完整跑一遍流程
    list_resp = client.get("/api/v1/approvals/?limit=1&sync=true")
    task_id = list_resp.json()["data"][0]["id"]

    client.post(
        "/api/v1/attachments/download",
        json={"task_id": task_id, "attachment_id": "att-001", "file_name": "合同.docx"},
    )
    client.post(f"/api/v1/documents/parse/{task_id}")
    client.post(f"/api/v1/rules/run/{task_id}")
    client.post("/api/v1/results/save", json={"task_id": task_id, "auto_run_rules": False})
    client.post(f"/api/v1/comments/write/{task_id}")

    # 查询该任务的所有日志
    logs_resp = client.get(f"/api/v1/logs/task/{task_id}?limit=100")
    logs = logs_resp.json()["data"]

    # 应包含多个模块的日志
    log_types = {log["log_type"] for log in logs}
    assert "M01" in log_types  # 审批拉取
    assert "M02" in log_types  # 附件下载
    assert "M04" in log_types  # 文档解析
    assert "M06" in log_types  # 规则审查
    assert "M07" in log_types  # 结果保存
    assert "M08" in log_types  # 评论回写


def test_dedup_across_multiple_syncs(client: TestClient):
    """多次同步同一批审批单应去重"""
    r1 = client.get("/api/v1/approvals/?limit=10&sync=true")
    r2 = client.get("/api/v1/approvals/?limit=10&sync=true")
    r3 = client.get("/api/v1/approvals/?limit=10&sync=true")

    # 三次同步后仍应只有 10 条记录
    codes1 = {item["approval_code"] for item in r1.json()["data"]}
    codes2 = {item["approval_code"] for item in r2.json()["data"]}
    codes3 = {item["approval_code"] for item in r3.json()["data"]}

    assert codes1 == codes2 == codes3
    assert len(codes1) == 10
