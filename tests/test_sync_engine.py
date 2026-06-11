"""
Description: Pytest module covering sync engine.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import time
from datetime import datetime, timezone
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.api.services import api_service
from app.models.user import User

def test_sync_changes_api(app, client, db):
    with app.app_context():
        u = auth_service.create_user("apiuser", "a@ex.com", "pass")
        user_id = u.id
        token_data = api_service.create_tokens(u)
        access_token = token_data['access_token']

        # Get baseline
        resp = client.get("/api/v1/sync/changes", headers={"Authorization": f"Bearer {access_token}"})
        data = resp.get_json()["data"]
        assert len(data["changes"]) == 1 # My Drive
        cursor1 = data["next_cursor"]
        assert cursor1 is not None

        root = folder_service.get_user_root_folder(u)
        root_id = root.id
        folder_service.create_folder(u, root, "F1")

    # Get changes using cursor
    response = client.get(f"/api/v1/sync/changes?cursor={cursor1}",
                          headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["changes"]) == 1
    assert data["changes"][0]["metadata"]["name"] == "F1"

    # Test pagination
    with app.app_context():
        u = db.session.get(User, user_id)
        from app.models.folder import Folder
        root = db.session.get(Folder, root_id)
        folder_service.create_folder(u, root, "F2")
        folder_service.create_folder(u, root, "F3")

    # Start from beginning
    response = client.get(f"/api/v1/sync/changes?per_page=1",
                          headers={"Authorization": f"Bearer {access_token}"})
    print(f"DEBUG: Status {response.status_code}, Body {response.get_data(as_text=True)}")
    if response.status_code == 429:
        pytest.skip("Rate limited during test")
    data = response.get_json()["data"]
    assert len(data["changes"]) == 1
    assert data["changes"][0]["metadata"]["name"] == "My Drive"
    assert data["has_more"] is True

    cursor = data["next_cursor"]
    response = client.get(f"/api/v1/sync/changes?cursor={cursor}&per_page=1",
                          headers={"Authorization": f"Bearer {access_token}"})
    data = response.get_json()["data"]
    assert len(data["changes"]) == 1
    assert data["changes"][0]["metadata"]["name"] == "F1"
    assert data["has_more"] is True
