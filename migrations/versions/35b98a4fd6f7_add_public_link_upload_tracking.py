"""
Description: Alembic migration script for 35b98a4fd6f7 add public link upload tracking.
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


revision = "35b98a4fd6f7"
down_revision = "92b4c454f962"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("public_links", schema=None) as batch_op:
        batch_op.add_column(sa.Column("max_upload_size_total_mb", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("upload_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("uploaded_bytes", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("last_accessed_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE public_links SET upload_count = 0 WHERE upload_count IS NULL")
    op.execute("UPDATE public_links SET uploaded_bytes = 0 WHERE uploaded_bytes IS NULL")


def downgrade():
    with op.batch_alter_table("public_links", schema=None) as batch_op:
        batch_op.drop_column("last_accessed_at")
        batch_op.drop_column("uploaded_bytes")
        batch_op.drop_column("upload_count")
        batch_op.drop_column("max_upload_size_total_mb")
