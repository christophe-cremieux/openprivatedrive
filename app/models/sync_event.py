"""
Description: Defines the SQLAlchemy model SyncEvent.
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

class SyncEvent(db.Model):
    __tablename__ = "sync_events"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resource_type = db.Column(db.String(20), nullable=False) # 'file' or 'folder'
    resource_id = db.Column(db.Integer, nullable=False)
    resource_uuid = db.Column(db.String(36), nullable=False)
    action = db.Column(db.String(20), nullable=False) # 'created', 'updated', 'deleted', 'moved', 'shared'
    event_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    metadata_json = db.Column(db.JSON, nullable=True)

    user = db.relationship("User", backref=db.backref("sync_events", lazy=True))

    def __repr__(self):
        return f"<SyncEvent {self.action} on {self.resource_type}:{self.resource_id} for user:{self.user_id}>"
