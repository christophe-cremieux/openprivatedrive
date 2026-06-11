"""
Description: Service layer implementation for PasswordService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from flask import current_app
from app.extensions import db

class PasswordService:
    @staticmethod
    def validate_password(password):
        """Validates password against policy."""
        if not password:
            return False, "Password is required."

        min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 12)
        if len(password) < min_length:
            return False, f"Password must be at least {min_length} characters long."

        # Add more complex checks here if needed (e.g. common passwords, mixed case, etc.)
        return True, None

    @staticmethod
    def generate_reset_token(user, admin_id=None):
        """Generates a password reset token for a user."""
        from app.models.password_reset_token import PasswordResetToken

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        expires_in = current_app.config.get("PASSWORD_RESET_TOKEN_MINUTES", 60)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=expires_in)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            created_by_admin_id=admin_id,
            expires_at=expires_at
        )

        db.session.add(reset_token)
        db.session.commit()

        return raw_token, expires_at

    @staticmethod
    def verify_reset_token(raw_token):
        """Verifies a reset token and returns the associated user if valid."""
        from app.models.password_reset_token import PasswordResetToken
        from app.models.user import User

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token_record = PasswordResetToken.query.filter_by(
            token_hash=token_hash,
            used_at=None
        ).populate_existing().first()

        if not token_record:
            return None, "Invalid or already used token."

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if token_record.expires_at < now:
            return None, "Token has expired."

        return token_record, None

password_service = PasswordService()
