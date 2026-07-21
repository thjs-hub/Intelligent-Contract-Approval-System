"""phase3: add ai_review_results table and semantic rules

Revision ID: 0002_phase3
Revises: 0001_init
Create Date: 2026-07-21

第三阶段数据库变更:
  1. 新增 ai_review_results 表 — 存储 LLM 智能审查结果
  2. 插入第三阶段语义规则种子数据 R012~R020
  3. 兼容第二阶段已有表结构，不修改任何已有表

执行:
  alembic upgrade head         # 升级
  alembic downgrade -1         # 回滚
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "0002_phase3"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """第三阶段数据库升级"""

    # 1. 创建 ai_review_results 表
    op.create_table(
        "ai_review_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("risk_items_json", mysql.JSON(), nullable=True),
        sa.Column("overall_assessment", sa.Text(), nullable=True),
        sa.Column("missing_clauses_json", mysql.JSON(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("token_usage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], name="fk_ai_review_task"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_ai_review_task_id"),
    )
    op.create_index("ix_ai_review_results_task_id", "ai_review_results", ["task_id"])

    # 2. 插入第三阶段新增语义匹配规则（match_mode='semantic'）
    # 这些规则利用 P3-2 语义匹配引擎，捕捉关键词/正则无法覆盖的语义级风险
    op.execute(
        """
        INSERT INTO review_rules (rule_code, rule_name, risk_level, rule_status, match_mode, match_text, suggestion_text) VALUES
        ('R012', '不平等条款检测', '高', 'enabled', 'semantic',
         '甲方有权单方面变更合同内容,甲方有权随时终止合同,甲方有权调整价格',
         '合同中存在甲方单方面权利条款，建议增加双方协商一致的前置条件。'),
        ('R013', '模糊表述检测', '中', 'enabled', 'semantic',
         '按实际情况确定,另行协商,视情况而定,原则上',
         '合同中存在模糊表述，建议明确具体标准或量化指标。'),
        ('R014', '责任限制条款', '中', 'enabled', 'semantic',
         '甲方不承担任何赔偿责任,赔偿金额不超过合同总额的百分之一',
         '责任限制条款可能对本方不利，建议调整赔偿上限。'),
        ('R015', '自动续约语义检测', '中', 'enabled', 'semantic',
         '合同到期后自动延续,无需另行通知即自动续约,默示续约',
         '检测到自动续约相关表述，建议增加到期前书面确认机制。'),
        ('R016', '数据安全义务不对等', '高', 'enabled', 'semantic',
         '乙方对数据泄露不承担任何责任,数据安全由乙方自行负责',
         '数据安全责任分配不对等，建议明确双方的数据保护义务。'),
        ('R017', '预付款比例过高', '高', 'enabled', 'regex',
         '预付款.*?([5-9]\\d|100)%|预付.*?([5-9]\\d|100)%',
         '预付款比例超过50%，风险较高，建议控制在30%以内。'),
        ('R018', '合同有效期过长', '中', 'enabled', 'regex',
         '有效期.*?(\\d{4,})年|合同期限.*?(\\d{4,})年',
         '合同有效期超过3年，建议设置中期评估机制。'),
        ('R019', '争议解决方式建议仲裁', '低', 'enabled', 'keyword',
         '诉讼,人民法院,法院管辖',
         '建议将争议解决方式改为仲裁，仲裁具有保密性和高效性。'),
        ('R020', '知识产权归属模糊', '高', 'enabled', 'semantic',
         '合同中未明确约定知识产权归属,技术成果归属不清晰',
         '知识产权归属约定不明确，可能引发权属争议，建议明确归属。')
        """
    )


def downgrade() -> None:
    """第三阶段数据库回滚"""

    # 1. 删除第三阶段新增的规则种子数据
    op.execute(
        """
        DELETE FROM review_rules
        WHERE rule_code IN (
            'R012', 'R013', 'R014', 'R015', 'R016',
            'R017', 'R018', 'R019', 'R020'
        )
        """
    )

    # 2. 删除 ai_review_results 表
    op.drop_index("ix_ai_review_results_task_id", table_name="ai_review_results")
    op.drop_table("ai_review_results")
