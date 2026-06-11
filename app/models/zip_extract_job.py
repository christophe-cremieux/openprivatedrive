"""
Description: Defines the SQLAlchemy model ZipExtractJob.
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

class ZipExtractJob(db.Model):
    __tablename__ = "zip_extract_jobs"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    zip_file_id = db.Column(db.Integer, db.ForeignKey("files.id"), nullable=False)
    destination_folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    status = db.Column(db.String(25), default='queued', index=True) # queued, processing, completed, completed_with_errors, failed
    summary_json = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("zip_extract_jobs", lazy=True))
    zip_file = db.relationship("File", foreign_keys=[zip_file_id])
    destination_folder = db.relationship("Folder", foreign_keys=[destination_folder_id])

    def __repr__(self):
        return f"<ZipExtractJob {self.uuid} - {self.status}>"
