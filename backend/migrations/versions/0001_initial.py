"""Create market data and audit event tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(28, 10), nullable=False),
        sa.Column("high", sa.Numeric(28, 10), nullable=False),
        sa.Column("low", sa.Numeric(28, 10), nullable=False),
        sa.Column("close", sa.Numeric(28, 10), nullable=False),
        sa.Column("volume", sa.Numeric(28, 10), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.UniqueConstraint("venue", "symbol", "interval", "open_time"),
    )
    op.create_index("ix_candles_symbol", "candles", ["symbol"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.String(4000), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("ix_candles_symbol", table_name="candles")
    op.drop_table("candles")
