"""add chat_search_results.summary

Revision ID: 1cc3c839b4ed
Revises: 8dbddb8df0fa
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1cc3c839b4ed'
down_revision: Union[str, Sequence[str], None] = '8dbddb8df0fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_search_results', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_search_results', 'summary')
