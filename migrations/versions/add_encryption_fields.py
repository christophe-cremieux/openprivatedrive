"""
Description: Alembic migration script for add encryption fields.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4caaa38d1e3'
down_revision = 'b6a36f51c526'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add columns as nullable first
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_encrypted', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('encryption_version', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('encryption_kdf', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('encryption_salt', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('encryption_nonce', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('encryption_metadata', sa.JSON(), nullable=True))
        batch_op.create_index(batch_op.f('ix_files_is_encrypted'), ['is_encrypted'], unique=False)

    # 2. Backfill existing rows
    op.execute("UPDATE files SET is_encrypted = 0 WHERE is_encrypted IS NULL")

    # 3. Make is_encrypted non-nullable with server default
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.alter_column('is_encrypted',
               existing_type=sa.Boolean(),
               nullable=False,
               server_default=sa.text('0'))

def downgrade():
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_files_is_encrypted'))
        batch_op.drop_column('encryption_metadata')
        batch_op.drop_column('encryption_nonce')
        batch_op.drop_column('encryption_salt')
        batch_op.drop_column('encryption_kdf')
        batch_op.drop_column('encryption_version')
        batch_op.drop_column('is_encrypted')
