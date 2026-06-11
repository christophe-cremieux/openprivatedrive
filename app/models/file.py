"""
Description: Defines the SQLAlchemy model File.
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

class File(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    extension = db.Column(db.String(20), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256_hash = db.Column(db.String(64), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    version_number = db.Column(db.Integer, default=1)
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    is_starred = db.Column(db.Boolean, default=False)
    is_quarantined = db.Column(db.Boolean, default=False, index=True)
    scan_status = db.Column(db.String(20), default='pending') # pending, clean, infected, failed
    scanned_at = db.Column(db.DateTime, nullable=True)
    antivirus_signature = db.Column(db.String(255), nullable=True)
    antivirus_error = db.Column(db.Text, nullable=True)
    is_encrypted = db.Column(db.Boolean, default=False, index=True, nullable=False, server_default=db.text('0'))
    encryption_version = db.Column(db.String(20), nullable=True)
    encryption_kdf = db.Column(db.String(20), nullable=True)
    encryption_salt = db.Column(db.String(128), nullable=True)
    encryption_nonce = db.Column(db.String(128), nullable=True)
    encryption_metadata = db.Column(db.JSON, nullable=True)
    preview_metadata = db.Column(db.JSON, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = db.relationship("User", backref=db.backref("files", lazy=True))
    folder = db.relationship("Folder", backref=db.backref("files", lazy=True))

    __table_args__ = (
        db.Index('ix_files_owner_folder_deleted', 'owner_id', 'folder_id', 'is_deleted'),
    )

    def __repr__(self):
        return f"<File {self.original_filename}>"
