"""
Description: Defines the SQLAlchemy model UploadSession.
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

class UploadSession(db.Model):
    __tablename__ = "upload_sessions"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    total_size = db.Column(db.BigInteger, nullable=False)
    total_chunks = db.Column(db.Integer, nullable=False)
    completed_chunks = db.Column(db.JSON, default=list) # List of indices
    sha256_hash = db.Column(db.String(64), nullable=False)
    relative_path = db.Column(db.String(1024), nullable=True)
    status = db.Column(db.String(20), default='active') # 'active', 'completed', 'failed'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", backref=db.backref("upload_sessions", lazy=True))
    folder = db.relationship("Folder", backref=db.backref("upload_sessions", lazy=True))

    def __repr__(self):
        return f"<UploadSession {self.filename} ({self.uuid[:8]})>"
