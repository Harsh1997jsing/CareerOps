"""add chat_search_results

Revision ID: 8dbddb8df0fa
Revises: 278f8db534a1
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8dbddb8df0fa'
down_revision: Union[str, Sequence[str], None] = '278f8db534a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('chat_search_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('source_job_id', sa.String(), nullable=True),
    sa.Column('company', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('employment_type', sa.String(), nullable=True),
    sa.Column('salary_min', sa.Integer(), nullable=True),
    sa.Column('salary_max', sa.Integer(), nullable=True),
    sa.Column('posted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_search_results_session_id'), 'chat_search_results', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_search_results_created_at'), 'chat_search_results', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chat_search_results_created_at'), table_name='chat_search_results')
    op.drop_index(op.f('ix_chat_search_results_session_id'), table_name='chat_search_results')
    op.drop_table('chat_search_results')
