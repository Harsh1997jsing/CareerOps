"""add unique constraint on applications.job_id

Revision ID: ae83e841285b
Revises: 1512aaa2ef50
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ae83e841285b'
down_revision: Union[str, Sequence[str], None] = '1512aaa2ef50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A full code audit pass found create_application()'s get-or-create
    # (app/services/applications.py) had no DB-level constraint backing
    # it — two concurrent POST /jobs/{id}/documents for the same job
    # could each pass the "does one already exist" check before either
    # committed, creating two Application rows for one job. De-duplicate
    # first (keep the oldest row per job_id) so the constraint below
    # applies cleanly regardless of what an existing database already has.
    op.execute(
        "DELETE FROM applications "
        "WHERE id NOT IN (SELECT MIN(id) FROM applications GROUP BY job_id)"
    )
    op.create_unique_constraint('uq_applications_job_id', 'applications', ['job_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_applications_job_id', 'applications', type_='unique')
