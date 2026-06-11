"""
Description: Provides API service logic and backend business rules.
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
from app.extensions import db
from app.models.api_token import ApiToken

class ApiService:
    ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
    REFRESH_TOKEN_LIFETIME = timedelta(days=30)

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def create_tokens(user, device_id=None, device_name=None, commit=True):
        """Generates a new access and refresh token pair."""
        access_token_raw = secrets.token_urlsafe(32)
        refresh_token_raw = secrets.token_urlsafe(32)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        access_token = ApiToken(
            user_id=user.id,
            device_id=device_id,
            device_name=device_name,
            token_hash=ApiService._hash_token(access_token_raw),
            token_type='access',
            expires_at=(now + ApiService.ACCESS_TOKEN_LIFETIME).replace(tzinfo=None)
        )

        refresh_token = ApiToken(
            user_id=user.id,
            device_id=device_id,
            device_name=device_name,
            token_hash=ApiService._hash_token(refresh_token_raw),
            token_type='refresh',
            expires_at=(now + ApiService.REFRESH_TOKEN_LIFETIME).replace(tzinfo=None)
        )

        db.session.add(access_token)
        db.session.add(refresh_token)
        if commit:
            db.session.commit()

        return {
            "access_token": access_token_raw,
            "refresh_token": refresh_token_raw,
            "expires_in": int(ApiService.ACCESS_TOKEN_LIFETIME.total_seconds()),
            "refresh_expires_in": int(ApiService.REFRESH_TOKEN_LIFETIME.total_seconds())
        }

    @staticmethod
    def refresh_access_token(refresh_token_raw):
        """Issues a new access token AND a new refresh token (rotation)."""
        token_hash = ApiService._hash_token(refresh_token_raw)
        token_record = ApiToken.query.filter_by(token_hash=token_hash, token_type='refresh', revoked_at=None).first()

        if not token_record:
            return None

        # SQLite naive datetime handling (assuming UTC)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = token_record.expires_at.replace(tzinfo=None) if token_record.expires_at.tzinfo else token_record.expires_at

        if expires_at < now:
            return None

        # 1. Revoke the old refresh token (Rotation)
        token_record.revoked_at = now

        # 2. Issue new pair (atomically)
        result = ApiService.create_tokens(token_record.user, token_record.device_id, token_record.device_name, commit=True)

        from app.services.activity_log_service import activity_log_service
        activity_log_service.log_activity(token_record.user_id, 'api_token_refresh', metadata={'device_id': token_record.device_id})

        return result

    @staticmethod
    def revoke_tokens(user, device_id=None):
        """Revokes all tokens for a user/device."""
        query = ApiToken.query.filter_by(user_id=user.id, revoked_at=None)
        if device_id:
            query = query.filter_by(device_id=device_id)

        tokens = query.all()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for t in tokens:
            t.revoked_at = now

        db.session.commit()

    @staticmethod
    def validate_token(token_raw, token_type='access'):
        """Validates an API token."""
        token_hash = ApiService._hash_token(token_raw)
        token_record = (
            ApiToken.query
            .join(ApiToken.user)
            .filter(
                ApiToken.token_hash == token_hash,
                ApiToken.token_type == token_type,
                ApiToken.revoked_at.is_(None),
                ApiToken.user.has(is_active=True),
            )
            .populate_existing()
            .first()
        )

        if not token_record:
            return None

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = token_record.expires_at.replace(tzinfo=None) if token_record.expires_at.tzinfo else token_record.expires_at

        if expires_at < now:
            return None

        if not token_record.user or not token_record.user.is_active:
            return None

        token_record.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

        return token_record.user

api_service = ApiService()
