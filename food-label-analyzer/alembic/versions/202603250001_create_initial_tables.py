"""create_initial_tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "202603250001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    task_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        name="task_status",
        create_type=False,
    )
    verification_type = postgresql.ENUM(
        "register",
        "reset_password",
        name="verification_type",
        create_type=False,
    )
    bind = op.get_bind()
    task_status.create(bind, checkfirst=True)
    verification_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_is_active", "users", ["is_active"], unique=False)

    op.create_table(
        "email_verifications",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(length=6),
            nullable=False,
        ),
        sa.Column(
            "type",
            verification_type,
            nullable=False,
        ),
        sa.Column(
            "is_used",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "expired_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_email_verifications_email_type",
        "email_verifications",
        ["email", "type"],
        unique=False,
    )
    op.create_index(
        "idx_email_verifications_expired_at",
        "email_verifications",
        ["expired_at"],
        unique=False,
    )

    op.create_table(
        "analysis_tasks",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "image_url",
            sa.String(length=1024),
            nullable=False,
        ),
        sa.Column(
            "image_key",
            sa.String(length=512),
            nullable=False,
        ),
        sa.Column(
            "status",
            task_status,
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "celery_task_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analysis_tasks_user_id", "analysis_tasks", ["user_id"], unique=False)
    op.create_index("idx_analysis_tasks_status", "analysis_tasks", ["status"], unique=False)
    op.create_index(
        "idx_analysis_tasks_user_status",
        "analysis_tasks",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_analysis_tasks_created_at",
        "analysis_tasks",
        [sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "is_used",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "expired_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(
        "idx_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "idx_password_reset_tokens_expired_at",
        "password_reset_tokens",
        ["expired_at"],
        unique=False,
    )

    op.create_table(
        "reports",
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingredients_text",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "nutrition_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "nutrition_parse_source",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "rag_results_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "llm_output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "score",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "artifact_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_reports_score_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index(
        "idx_reports_user_id_created_at",
        "reports",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index("idx_reports_score", "reports", ["score"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_reports_score", table_name="reports")
    op.drop_index("idx_reports_user_id_created_at", table_name="reports")
    op.drop_table("reports")

    op.drop_index("idx_password_reset_tokens_expired_at", table_name="password_reset_tokens")
    op.drop_index("idx_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("idx_analysis_tasks_created_at", table_name="analysis_tasks")
    op.drop_index("idx_analysis_tasks_user_status", table_name="analysis_tasks")
    op.drop_index("idx_analysis_tasks_status", table_name="analysis_tasks")
    op.drop_index("idx_analysis_tasks_user_id", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")

    op.drop_index("idx_email_verifications_expired_at", table_name="email_verifications")
    op.drop_index("idx_email_verifications_email_type", table_name="email_verifications")
    op.drop_table("email_verifications")

    op.drop_index("idx_users_is_active", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM(name="verification_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="task_status").drop(bind, checkfirst=True)
