"""add sovereign_vetoes and data_truth_audits tables

Revision ID: 3f13bb8da8a7
Revises: fcc02d8e6e64
Create Date: 2026-03-06 14:18:44.578012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f13bb8da8a7'
down_revision: Union[str, Sequence[str], None] = 'fcc02d8e6e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sovereign_vetoes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('country_code', sa.String(2), nullable=False, index=True),
        sa.Column('veto_type', sa.String(50), nullable=False, index=True),
        sa.Column('severity', sa.String(20), nullable=False, server_default='FULL_BLOCK'),
        sa.Column('issued_by', sa.String(100), nullable=False),
        sa.Column('issued_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('reference_number', sa.String(100), nullable=True),
        sa.Column('legal_basis', sa.String(200), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('max_loan_cap_usd', sa.Float(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1', index=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_by', sa.String(100), nullable=True),
        sa.Column('revoked_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('revocation_reason', sa.Text(), nullable=True),
        sa.Column('human_review_required', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('country_code', 'veto_type', 'effective_date', name='uq_veto_country_type_date'),
    )

    op.create_table(
        'data_truth_audits',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('country_code', sa.String(2), nullable=False, index=True),
        sa.Column('metric_name', sa.String(100), nullable=False, index=True),
        sa.Column('record_table', sa.String(50), nullable=True),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('field_name', sa.String(50), nullable=True),
        sa.Column('source_a', sa.String(100), nullable=False),
        sa.Column('source_b', sa.String(100), nullable=False),
        sa.Column('value_a', sa.Float(), nullable=False),
        sa.Column('value_b', sa.Float(), nullable=False),
        sa.Column('divergence_pct', sa.Float(), nullable=False),
        sa.Column('z_score', sa.Float(), nullable=True),
        sa.Column('historical_mean', sa.Float(), nullable=True),
        sa.Column('historical_std', sa.Float(), nullable=True),
        sa.Column('source_a_date', sa.DateTime(), nullable=True),
        sa.Column('source_b_date', sa.DateTime(), nullable=True),
        sa.Column('staleness_hours', sa.Float(), nullable=True),
        sa.Column('is_stale', sa.Boolean(), server_default='0'),
        sa.Column('verdict', sa.String(20), nullable=False),
        sa.Column('confidence_before', sa.Float(), nullable=True),
        sa.Column('confidence_after', sa.Float(), nullable=True),
        sa.Column('truth_score', sa.Float(), server_default='1.0'),
        sa.Column('veto_id', sa.Integer(), sa.ForeignKey('sovereign_vetoes.id'), nullable=True, index=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('audited_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('country_code', 'metric_name', 'audited_at', name='uq_truth_audit'),
    )


def downgrade() -> None:
    op.drop_table('data_truth_audits')
    op.drop_table('sovereign_vetoes')
