"""add reconciliation and world news tables

Revision ID: fcc02d8e6e64
Revises: 5265dbdea763
Create Date: 2026-03-04 23:45:25.037597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcc02d8e6e64'
down_revision: Union[str, Sequence[str], None] = '5265dbdea763'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """Check if a table already exists (handles dev SQLite with create_all)."""
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    """Create 7 missing tables: 4 reconciliation + 3 world news."""

    # ── Reconciliation tables ───────────────────────────────────────

    if not _table_exists('data_source_health'):
        op.create_table(
            'data_source_health',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('source_name', sa.String(50), nullable=False, unique=True),
            sa.Column('last_fetch_at', sa.DateTime(), nullable=True),
            sa.Column('last_success_at', sa.DateTime(), nullable=True),
            sa.Column('fetch_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('avg_latency_ms', sa.Float(), server_default='0.0'),
            sa.Column('reliability_score', sa.Float(), server_default='1.0'),
            sa.Column('status', sa.String(15), nullable=False, server_default='UNKNOWN'),
            sa.Column('last_error_message', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_data_source_health_id', 'data_source_health', ['id'])
        op.create_index('ix_data_source_health_source_name', 'data_source_health', ['source_name'], unique=True)

    if not _table_exists('data_quarantine'):
        op.create_table(
            'data_quarantine',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('table_name', sa.String(50), nullable=False),
            sa.Column('record_id', sa.Integer(), nullable=False),
            sa.Column('country_code', sa.String(2), nullable=True),
            sa.Column('anomaly_type', sa.String(30), nullable=False),
            sa.Column('anomaly_detail', sa.Text(), nullable=False),
            sa.Column('severity', sa.String(10), nullable=False),
            sa.Column('status', sa.String(15), nullable=False, server_default='PENDING'),
            sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_data_quarantine_id', 'data_quarantine', ['id'])
        op.create_index('ix_data_quarantine_table_name', 'data_quarantine', ['table_name'])
        op.create_index('ix_data_quarantine_record_id', 'data_quarantine', ['record_id'])
        op.create_index('ix_data_quarantine_country_code', 'data_quarantine', ['country_code'])
        op.create_index('ix_data_quarantine_anomaly_type', 'data_quarantine', ['anomaly_type'])
        op.create_index('ix_data_quarantine_status', 'data_quarantine', ['status'])

    if not _table_exists('data_lineage'):
        op.create_table(
            'data_lineage',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('target_table', sa.String(50), nullable=False),
            sa.Column('target_id', sa.Integer(), nullable=False),
            sa.Column('source_table', sa.String(50), nullable=False),
            sa.Column('source_id', sa.Integer(), nullable=False),
            sa.Column('contribution_weight', sa.Float(), nullable=False),
            sa.Column('snapshot_value', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_data_lineage_id', 'data_lineage', ['id'])
        op.create_index('ix_data_lineage_target_table', 'data_lineage', ['target_table'])
        op.create_index('ix_data_lineage_target_id', 'data_lineage', ['target_id'])

    if not _table_exists('reconciliation_runs'):
        op.create_table(
            'reconciliation_runs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('run_type', sa.String(20), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('records_checked', sa.Integer(), server_default='0'),
            sa.Column('anomalies_found', sa.Integer(), server_default='0'),
            sa.Column('quarantined', sa.Integer(), server_default='0'),
            sa.Column('auto_resolved', sa.Integer(), server_default='0'),
            sa.Column('summary_json', sa.Text(), nullable=True),
        )
        op.create_index('ix_reconciliation_runs_id', 'reconciliation_runs', ['id'])

    # ── World News Intelligence tables ──────────────────────────────

    if not _table_exists('world_news_events'):
        op.create_table(
            'world_news_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('event_type', sa.String(40), nullable=False),
            sa.Column('headline', sa.String(500), nullable=False),
            sa.Column('summary', sa.Text(), server_default=''),
            sa.Column('source_url', sa.String(500), nullable=True),
            sa.Column('source_name', sa.String(100), nullable=True),
            sa.Column('source_region', sa.String(50), nullable=True),
            sa.Column('relevance_score', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('relevance_layer1_keyword', sa.Float(), server_default='0.0'),
            sa.Column('relevance_layer2_supply_chain', sa.Float(), server_default='0.0'),
            sa.Column('relevance_layer3_transmission', sa.Float(), server_default='0.0'),
            sa.Column('keywords_matched', sa.Text(), server_default='[]'),
            sa.Column('global_magnitude', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('detected_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='1'),
            sa.Column('cascaded', sa.Boolean(), server_default='0'),
            sa.UniqueConstraint('headline', 'source_name', 'detected_at', name='uq_world_news_dedup'),
        )
        op.create_index('ix_world_news_events_id', 'world_news_events', ['id'])
        op.create_index('ix_world_news_events_event_type', 'world_news_events', ['event_type'])
        op.create_index('ix_world_news_events_detected_at', 'world_news_events', ['detected_at'])
        op.create_index('ix_world_news_events_expires_at', 'world_news_events', ['expires_at'])
        op.create_index('ix_world_news_events_is_active', 'world_news_events', ['is_active'])
        op.create_index('ix_world_news_events_cascaded', 'world_news_events', ['cascaded'])

    if not _table_exists('news_impact_assessments'):
        op.create_table(
            'news_impact_assessments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('world_news_event_id', sa.Integer(), nullable=False),
            sa.Column('country_code', sa.String(2), nullable=False),
            sa.Column('direct_impact', sa.Float(), server_default='0.0'),
            sa.Column('indirect_impact', sa.Float(), server_default='0.0'),
            sa.Column('systemic_impact', sa.Float(), server_default='0.0'),
            sa.Column('country_magnitude', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('transmission_channel', sa.String(100), nullable=True),
            sa.Column('explanation', sa.Text(), server_default=''),
            sa.Column('news_event_created', sa.Boolean(), server_default='0'),
            sa.Column('news_event_id', sa.Integer(), nullable=True),
            sa.Column('assessed_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('world_news_event_id', 'country_code', name='uq_impact_event_country'),
        )
        op.create_index('ix_news_impact_assessments_id', 'news_impact_assessments', ['id'])
        op.create_index('ix_news_impact_assessments_world_news_event_id', 'news_impact_assessments', ['world_news_event_id'])
        op.create_index('ix_news_impact_assessments_country_code', 'news_impact_assessments', ['country_code'])

    if not _table_exists('daily_news_briefings'):
        op.create_table(
            'daily_news_briefings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('briefing_date', sa.Date(), nullable=False, unique=True),
            sa.Column('total_global_events', sa.Integer(), server_default='0'),
            sa.Column('high_relevance_events', sa.Integer(), server_default='0'),
            sa.Column('countries_affected', sa.Integer(), server_default='0'),
            sa.Column('top_events_json', sa.Text(), server_default='[]'),
            sa.Column('country_exposure_json', sa.Text(), server_default='{}'),
            sa.Column('trend_indicators_json', sa.Text(), server_default='{}'),
            sa.Column('watchlist_json', sa.Text(), server_default='[]'),
            sa.Column('generated_at', sa.DateTime(), nullable=True),
            sa.Column('engine_version', sa.String(10), server_default='1.0'),
        )
        op.create_index('ix_daily_news_briefings_id', 'daily_news_briefings', ['id'])
        op.create_index('ix_daily_news_briefings_briefing_date', 'daily_news_briefings', ['briefing_date'], unique=True)


def downgrade() -> None:
    """Drop 7 tables."""
    op.drop_table('daily_news_briefings')
    op.drop_table('news_impact_assessments')
    op.drop_table('world_news_events')
    op.drop_table('reconciliation_runs')
    op.drop_table('data_lineage')
    op.drop_table('data_quarantine')
    op.drop_table('data_source_health')
