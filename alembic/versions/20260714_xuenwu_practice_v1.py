"""xuenwu practice v1 tables

Revision ID: 20260714_xuenwu_prac
Revises: 20260712_xuenwu_review
Create Date: 2026-07-14

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260714_xuenwu_prac"
down_revision = "20260712_xuenwu_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False, server_default="current_progress"),
        sa.Column("target_node_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generated"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("config_version", sa.String(length=40), nullable=False, server_default="v1.0"),
        sa.Column("ai_model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("ai_generation_version", sa.String(length=40), nullable=False, server_default="xuenwu-practice-v1"),
        sa.Column("source_plan", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("feedback", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_sessions_user_session", "practice_sessions", ["user_id", "session_id"], unique=False)
    op.create_index("ix_practice_sessions_created", "practice_sessions", ["created_at"], unique=False)

    op.create_table(
        "practice_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("practice_session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("generation_basis", sa.String(length=40), nullable=False, server_default="CURRENT_NODE"),
        sa.Column("question_type", sa.String(length=30), nullable=False, server_default="short_answer"),
        sa.Column("difficulty", sa.String(length=20), nullable=False, server_default="basic"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("standard_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("answer_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("auto_gradable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("validation_errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="ai"),
        sa.Column("ai_model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["practice_session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_items_practice", "practice_items", ["practice_session_id"], unique=False)
    op.create_index("ix_practice_items_node", "practice_items", ["node_id"], unique=False)
    op.create_index("ix_practice_items_basis", "practice_items", ["generation_basis"], unique=False)

    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("practice_item_id", sa.String(length=64), nullable=False),
        sa.Column("practice_session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("student_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_suggested_result", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("ai_feedback", sa.Text(), nullable=False, server_default=""),
        sa.Column("student_confirmed_result", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("final_result", sa.String(length=20), nullable=False, server_default="skipped"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_reason", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("used_hint", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("viewed_answer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["practice_item_id"], ["practice_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["practice_session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_practice_attempts_item", "practice_attempts", ["practice_item_id"], unique=False)
    op.create_index("ix_practice_attempts_user", "practice_attempts", ["user_id"], unique=False)
    op.create_index("ix_practice_attempts_result", "practice_attempts", ["final_result"], unique=False)

    op.create_table(
        "node_mastery",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("mastery_state", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("mastery_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_or_hard_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_window", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("correct_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_mastery_user_session", "node_mastery", ["user_id", "session_id"], unique=False)
    op.create_index("ix_node_mastery_node", "node_mastery", ["node_id"], unique=False)

    op.add_column("wrong_questions", sa.Column("practice_item_id", sa.String(length=64), nullable=True))
    op.add_column("wrong_questions", sa.Column("practice_mode", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("wrong_questions", sa.Column("question_type", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("wrong_questions", sa.Column("difficulty", sa.String(length=20), nullable=False, server_default=""))
    op.add_column("wrong_questions", sa.Column("result", sa.String(length=20), nullable=False, server_default="wrong"))
    op.add_column("wrong_questions", sa.Column("error_reason", sa.String(length=40), nullable=False, server_default=""))
    op.add_column("wrong_questions", sa.Column("source", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("wrong_questions", sa.Column("first_wrong_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wrong_questions", sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "wrong_questions",
        sa.Column("consecutive_correct_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_wrong_questions_practice_item_id",
        "wrong_questions",
        "practice_items",
        ["practice_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_wrong_questions_practice_item_id", "wrong_questions", type_="foreignkey")
    op.drop_column("wrong_questions", "consecutive_correct_count")
    op.drop_column("wrong_questions", "last_practiced_at")
    op.drop_column("wrong_questions", "first_wrong_at")
    op.drop_column("wrong_questions", "source")
    op.drop_column("wrong_questions", "error_reason")
    op.drop_column("wrong_questions", "result")
    op.drop_column("wrong_questions", "difficulty")
    op.drop_column("wrong_questions", "question_type")
    op.drop_column("wrong_questions", "practice_mode")
    op.drop_column("wrong_questions", "practice_item_id")

    op.drop_index("ix_node_mastery_node", table_name="node_mastery")
    op.drop_index("ix_node_mastery_user_session", table_name="node_mastery")
    op.drop_table("node_mastery")

    op.drop_index("ix_practice_attempts_result", table_name="practice_attempts")
    op.drop_index("ix_practice_attempts_user", table_name="practice_attempts")
    op.drop_index("ix_practice_attempts_item", table_name="practice_attempts")
    op.drop_table("practice_attempts")

    op.drop_index("ix_practice_items_basis", table_name="practice_items")
    op.drop_index("ix_practice_items_node", table_name="practice_items")
    op.drop_index("ix_practice_items_practice", table_name="practice_items")
    op.drop_table("practice_items")

    op.drop_index("ix_practice_sessions_created", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_user_session", table_name="practice_sessions")
    op.drop_table("practice_sessions")
