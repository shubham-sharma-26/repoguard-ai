"""Create persistent analysis history."""
from alembic import op
import sqlalchemy as sa

revision = "0001_analysis_runs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("analysis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False))
    for column in ("owner", "name", "commit_sha", "status", "analyzed_at"):
        op.create_index(f"ix_analysis_runs_{column}", "analysis_runs", [column])


def downgrade() -> None:
    for column in ("owner", "name", "commit_sha", "status", "analyzed_at"):
        op.drop_index(f"ix_analysis_runs_{column}", table_name="analysis_runs")
    op.drop_table("analysis_runs")
