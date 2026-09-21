"""add generated_documents.content_json

Revision ID: 1512aaa2ef50
Revises: eefb6be2ee44
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1512aaa2ef50'
down_revision: Union[str, Sequence[str], None] = 'eefb6be2ee44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generated_documents', sa.Column('content_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generated_documents', 'content_json')
