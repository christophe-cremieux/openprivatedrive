"""
Description: Defines the SQLAlchemy model PublicLink.
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

class PublicLink(db.Model):
    __tablename__ = "public_links"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    resource_type = db.Column(db.String(20), nullable=False) # 'file' or 'folder'
    resource_id = db.Column(db.Integer, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    password_required = db.Column(db.Boolean, default=False)
    one_time_password = db.Column(db.Boolean, default=False)
    link_type = db.Column(db.String(20), default='download') # 'download' or 'upload'
    max_files = db.Column(db.Integer, default=25)
    max_upload_size_mb = db.Column(db.Integer, default=100)
    max_upload_size_total_mb = db.Column(db.Integer, nullable=True)
    max_downloads = db.Column(db.Integer, nullable=True)
    download_count = db.Column(db.Integer, default=0)
    upload_count = db.Column(db.Integer, default=0)
    uploaded_bytes = db.Column(db.BigInteger, default=0)
    expires_at = db.Column(db.DateTime, nullable=True)
    last_accessed_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    created_by = db.relationship("User", backref=db.backref("public_links", lazy=True))

    def __repr__(self):
        return f"<PublicLink {self.resource_type}:{self.resource_id} token_hash:{self.token_hash[:8]}>"
