"""add xuenwu review tables

Revision ID: 20260712_xuenwu_review
Revises: 20260603_add_context_summary
Create Date: 2026-07-12

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260712_xuenwu_review"
down_revision = "20260603_add_context_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("item_type", sa.String(length=30), nullable=False, server_default="question"),
        sa.Column("difficulty", sa.String(length=20), nullable=False, server_default="basic"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="ai"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_items_user_session", "review_items", ["user_id", "session_id"], unique=False)
    op.create_index("ix_review_items_node", "review_items", ["node_id"], unique=False)

    op.create_table(
        "review_attempts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("review_item_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_attempts_item", "review_attempts", ["review_item_id"], unique=False)
    op.create_index("ix_review_attempts_user", "review_attempts", ["user_id"], unique=False)

    op.create_table(
        "wrong_questions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("review_item_id", sa.String(length=64), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("student_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("correct_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="unresolved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wrong_questions_user_session", "wrong_questions", ["user_id", "session_id"], unique=False)
    op.create_index("ix_wrong_questions_node", "wrong_questions", ["node_id"], unique=False)

    op.create_table(
        "learning_reflections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("wrong_question_id", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wrong_question_id"], ["wrong_questions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_reflections_user_session",
        "learning_reflections",
        ["user_id", "session_id"],
        unique=False,
    )
    op.create_index("ix_learning_reflections_wrong", "learning_reflections", ["wrong_question_id"], unique=False)

    op.create_table(
        "assistant_suggestions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("suggestion_type", sa.String(length=30), nullable=False, server_default="review"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_suggestions_user_session",
        "assistant_suggestions",
        ["user_id", "session_id"],
        unique=False,
    )
    op.create_index("ix_assistant_suggestions_created", "assistant_suggestions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assistant_suggestions_created", table_name="assistant_suggestions")
    op.drop_index("ix_assistant_suggestions_user_session", table_name="assistant_suggestions")
    op.drop_table("assistant_suggestions")
    op.drop_index("ix_learning_reflections_wrong", table_name="learning_reflections")
    op.drop_index("ix_learning_reflections_user_session", table_name="learning_reflections")
    op.drop_table("learning_reflections")
    op.drop_index("ix_wrong_questions_node", table_name="wrong_questions")
    op.drop_index("ix_wrong_questions_user_session", table_name="wrong_questions")
    op.drop_table("wrong_questions")
    op.drop_index("ix_review_attempts_user", table_name="review_attempts")
    op.drop_index("ix_review_attempts_item", table_name="review_attempts")
    op.drop_table("review_attempts")
    op.drop_index("ix_review_items_node", table_name="review_items")
    op.drop_index("ix_review_items_user_session", table_name="review_items")
    op.drop_table("review_items")
