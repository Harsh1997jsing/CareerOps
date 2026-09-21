"""chat_search_results require source_job_id and location

Revision ID: eefb6be2ee44
Revises: 1cc3c839b4ed
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'eefb6be2ee44'
down_revision: Union[str, Sequence[str], None] = '1cc3c839b4ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('chat_search_results', 'source_job_id', existing_type=sa.String(), nullable=False)
    op.alter_column('chat_search_results', 'location', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('chat_search_results', 'location', existing_type=sa.String(), nullable=True)
    op.alter_column('chat_search_results', 'source_job_id', existing_type=sa.String(), nullable=True)
