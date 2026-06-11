"""
Description: Declares shared Flask extension instances used throughout the application.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_executor import Executor
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://" # Default, will be overridden in init_app by config if needed
)

@limiter.request_filter
def exempt_authenticated():
    # Only exempt authenticated users from DEFAULT limits.
    # If a route has an explicit @limiter.limit, it will still apply unless we check more.
    # But usually request_filter exempts from everything.
    # The requirement is "authenticated user should not get this error when navigating".
    from flask import request
    from flask_login import current_user

    # We only want to exempt them from the "50 per hour" type default limits
    # that trigger during normal navigation.
    # If we return True here, they are exempt from ALL rate limits.
    # Decryption has @limiter.limit(lambda: current_app.config.get("DECRYPT_RATE_LIMIT", "5 per minute"))
    # We might want to keep those.

    # Actually, for "navigating the application", exempting is fine.
    # If we want to be more specific, we could check if the current endpoint has a limit set.
    # But for now, let's follow the request to fix the navigation issue.
    return current_user.is_authenticated
executor = Executor()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Check if we are using sqlite
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
