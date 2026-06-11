"""
Description: Defines the SQLAlchemy model SystemStat.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from datetime import datetime, timezone
from app.extensions import db

class SystemStat(db.Model):
    __tablename__ = "system_stats"

    id = db.Column(db.Integer, primary_key=True)
    stat_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    stat_value = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    @staticmethod
    def get_stat(key, default=None):
        stat = SystemStat.query.filter_by(stat_key=key).first()
        return stat.stat_value if stat else default

    @staticmethod
    def set_stat(key, value):
        stat = SystemStat.query.filter_by(stat_key=key).first()
        if stat:
            stat.stat_value = value
            stat.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            stat = SystemStat(stat_key=key, stat_value=value)
            db.session.add(stat)
        db.session.commit()
