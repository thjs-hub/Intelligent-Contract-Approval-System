"""init: create all tables

Revision ID: 0001_init
Create Date: 2026-07-20

第二阶段初始迁移: 创建 8 张业务表。
执行: alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建全部业务表"""

    # 1. approval_tasks — 审批任务表
    op.create_table(
        "approval_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("approval_code", sa.String(length=128), nullable=False),
        sa.Column("approval_title", sa.String(length=512), nullable=True),
        sa.Column("applicant_name", sa.String(length=128), nullable=True),
        sa.Column(
            "task_status",
            sa.Enum("pending", "parsing", "reviewing", "blocked", "done", name="task_status_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "write_status",
            sa.Enum("not_written", "writing", "success", "failed", name="write_status_enum"),
            nullable=False,
            server_default="not_written",
        ),
        sa.Column("block_reason", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now() on update now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_code", name="uq_approval_tasks_approval_code"),
    )
    op.create_index("ix_approval_tasks_approval_code", "approval_tasks", ["approval_code"])

    # 2. approval_attachments — 附件表
    op.create_table(
        "approval_attachments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=True),
        sa.Column("file_type", sa.String(length=64), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("file_md5", sa.String(length=64), nullable=True, server_default=""),
        sa.Column("download_status", sa.String(length=32), nullable=True, server_default="pending"),
        sa.Column("download_error", sa.String(length=1024), nullable=True),
        sa.Column("external_attachment_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_attachments_task"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_attachments_task_id", "approval_attachments", ["task_id"])

    # 3. contract_parses — 合同解析结果表
    op.create_table(
        "contract_parses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("basic_info_json", mysql.JSON(), nullable=True),
        sa.Column("clause_info_json", mysql.JSON(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=True, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_parses_task"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_contract_parses_task_id"),
    )

    # 4. review_rules — 审查规则表
    op.create_table(
        "review_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_name", sa.String(length=256), nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("低", "中", "高", name="risk_level_enum"),
            nullable=False,
        ),
        sa.Column(
            "rule_status",
            sa.Enum("enabled", "disabled", name="rule_status_enum"),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column(
            "match_mode",
            sa.Enum("keyword", "regex", "semantic", name="match_mode_enum"),
            nullable=False,
        ),
        sa.Column("match_text", sa.Text(), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now() on update now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_code", name="uq_review_rules_rule_code"),
    )
    op.create_index("ix_review_rules_rule_code", "review_rules", ["rule_code"])

    # 5. rule_hits — 规则命中记录表
    op.create_table(
        "rule_hits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("evidence_position", sa.String(length=256), nullable=True),
        sa.Column("hit_status", sa.String(length=32), nullable=True, server_default="hit"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_hits_task"),
        sa.ForeignKeyConstraint(["rule_id"], ["review_rules.id"], name="fk_hits_rule"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_hits_task_id", "rule_hits", ["task_id"])

    # 6. review_results — 审查结果表
    op.create_table(
        "review_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "overall_risk_level",
            sa.Enum("低", "中", "高", name="result_risk_enum"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("focus_points_json", mysql.JSON(), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_results_task"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_review_results_task_id"),
    )

    # 7. comment_logs — 评论回写日志表
    op.create_table(
        "comment_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "write_status",
            sa.Enum(
                "not_written", "writing", "success", "failed", name="comment_status_enum"
            ),
            nullable=False,
            server_default="not_written",
        ),
        sa.Column("write_response_text", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_comments_task"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comment_logs_task_id", "comment_logs", ["task_id"])

    # 8. task_logs — 任务运行日志表
    op.create_table(
        "task_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "log_level",
            sa.Enum("INFO", "WARN", "ERROR", name="log_level_enum"),
            nullable=False,
            server_default="INFO",
        ),
        sa.Column("log_type", sa.String(length=64), nullable=True),
        sa.Column("log_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_logs_task"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_logs_task_id", "task_logs", ["task_id"])


def downgrade() -> None:
    """回滚: 删除全部业务表"""
    op.drop_table("task_logs")
    op.drop_table("comment_logs")
    op.drop_table("review_results")
    op.drop_table("rule_hits")
    op.drop_table("review_rules")
    op.drop_table("contract_parses")
    op.drop_table("approval_attachments")
    op.drop_table("approval_tasks")
