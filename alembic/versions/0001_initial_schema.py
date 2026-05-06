"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-06 18:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_mode", sa.String(length=120), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("best_score", sa.Float(), nullable=False),
        sa.Column("best_solution", sa.Text(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=False),
        sa.Column("ship_readiness", sa.String(length=40), nullable=False),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("validity_status", sa.String(length=40), nullable=False),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
    )

    op.create_table(
        "iterations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("tech_score", sa.Integer(), nullable=False),
        sa.Column("logic_score", sa.Integer(), nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("ship_readiness", sa.String(length=40), nullable=False),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("verification_score", sa.Float(), nullable=False),
        sa.Column("architect_model", sa.String(length=120), nullable=False),
        sa.Column("tech_model", sa.String(length=120), nullable=False),
        sa.Column("logic_model", sa.String(length=120), nullable=False),
        sa.Column("preflight_issues", sa.JSON(), nullable=False),
        sa.Column("tech_issues", sa.JSON(), nullable=False),
        sa.Column("logic_issues", sa.JSON(), nullable=False),
        sa.Column("janitor_summary", sa.Text(), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_iterations_run_id", "iterations", ["run_id"])

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("task_mode", sa.String(length=120), nullable=False),
        sa.Column("task_hash", sa.String(length=120), nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("memory_status", sa.String(length=40), nullable=False),
        sa.Column("consensus_score", sa.Float(), nullable=False),
        sa.Column("repair_patterns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_entries_run_id", "memory_entries", ["run_id"])
    op.create_index("ix_memory_entries_task_hash", "memory_entries", ["task_hash"])


def downgrade() -> None:
    op.drop_index("ix_memory_entries_task_hash", table_name="memory_entries")
    op.drop_index("ix_memory_entries_run_id", table_name="memory_entries")
    op.drop_table("memory_entries")
    op.drop_index("ix_iterations_run_id", table_name="iterations")
    op.drop_table("iterations")
    op.drop_table("runs")
