"""
Description: Defines the SQLAlchemy model Folder.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db

class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    is_root = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    is_starred = db.Column(db.Boolean, default=False)
    encrypt_new_uploads = db.Column(db.Boolean, default=False, nullable=False, server_default=db.text('0'))
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = db.relationship("User", backref=db.backref("folders", lazy=True))
    parent = db.relationship("Folder", remote_side=[id], backref=db.backref("children", lazy=True))

    __table_args__ = (
        db.Index('ix_folders_owner_parent_deleted', 'owner_id', 'parent_id', 'is_deleted'),
    )

    def __repr__(self):
        return f"<Folder {self.name}>"
