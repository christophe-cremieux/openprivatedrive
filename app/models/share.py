"""
Description: Defines the SQLAlchemy model Share.
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

class Share(db.Model):
    __tablename__ = "shares"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    resource_type = db.Column(db.String(20), nullable=False, index=True) # 'file' or 'folder'
    resource_id = db.Column(db.Integer, nullable=False, index=True)
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shared_with_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    permission = db.Column(db.String(20), nullable=False) # 'viewer', 'editor', 'manager'
    inherit_to_children = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    shared_by = db.relationship("User", foreign_keys=[shared_by_user_id], backref=db.backref("shares_given", lazy=True))
    shared_with = db.relationship("User", foreign_keys=[shared_with_user_id], backref=db.backref("shares_received", lazy=True))

    def __repr__(self):
        return f"<Share {self.resource_type}:{self.resource_id} with {self.shared_with_user_id}>"
