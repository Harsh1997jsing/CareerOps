"""add unique constraint on generated_documents (job_id, type, version)

Revision ID: 048a9efe0048
Revises: ae83e841285b
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '048a9efe0048'
down_revision: Union[str, Sequence[str], None] = 'ae83e841285b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A full code audit pass found persist_document()'s _next_version()
    # (app/services/document_generator.py) had no DB-level constraint
    # backing its per-(job, type) version counter — two concurrent
    # POST /jobs/{id}/documents (same type) could compute the same next
    # version before either committed, both writing the identical on-disk
    # filename (second write clobbers the first) and both inserting a row
    # claiming that version. De-duplicate first (keep the oldest row per
    # job_id/type/version) so the constraint below applies cleanly
    # regardless of what an existing database already has.
    op.execute(
        "DELETE FROM generated_documents "
        "WHERE id NOT IN (SELECT MIN(id) FROM generated_documents GROUP BY job_id, type, version)"
    )
    op.create_unique_constraint(
        'uq_generated_documents_job_type_version', 'generated_documents', ['job_id', 'type', 'version']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_generated_documents_job_type_version', 'generated_documents', type_='unique')
