"""
Description: Pytest module covering token rotation.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.api.services import api_service
from app.auth.services import auth_service
from app.models.api_token import ApiToken

def test_token_rotation_and_expiry(app, db):
    with app.app_context():
        user = auth_service.create_user("rotation", "rot@ex.com", "pass")

        # 1. Create initial tokens
        token_data = api_service.create_tokens(user, "dev1", "Device 1")
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["expires_in"] == 3600
        assert "refresh_expires_in" in token_data

        first_refresh_token = token_data["refresh_token"]

        # 2. Refresh
        new_token_data = api_service.refresh_access_token(first_refresh_token)
        assert new_token_data is not None
        assert new_token_data["access_token"] != token_data["access_token"]
        assert new_token_data["refresh_token"] != first_refresh_token

        # 3. Verify old refresh token is revoked
        old_token_record = ApiToken.query.filter_by(token_hash=api_service._hash_token(first_refresh_token)).first()
        assert old_token_record.revoked_at is not None

        # 4. Try to use old refresh token again (should fail)
        fail_data = api_service.refresh_access_token(first_refresh_token)
        assert fail_data is None
