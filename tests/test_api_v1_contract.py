"""
Description: Pytest module covering api v1 contract.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import io
from app.extensions import db
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.auth.services import auth_service
from app.api.services import api_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_api_contract"
    WTF_CSRF_ENABLED = False

@pytest.fixture
def app():
    app = create_app(TestConfig)
    if not os.path.exists(TestConfig.STORAGE_PATH):
        os.makedirs(TestConfig.STORAGE_PATH)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
    import shutil
    if os.path.exists(TestConfig.STORAGE_PATH):
        shutil.rmtree(TestConfig.STORAGE_PATH)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def api_auth(app):
    with app.app_context():
        user = auth_service.create_user("apiuser", "api@ex.com", "password")
        user_id = user.id
        token_data = api_service.create_tokens(user, "test_device", "Android Phone")
        return user_id, token_data['access_token'], token_data['refresh_token']

def test_api_folder_path(client, api_auth, app):
    user_id, token, _ = api_auth
    with app.app_context():
        u = db.session.get(User, user_id)
        root = Folder.query.filter_by(owner_id=u.id, is_root=True).first()
        f1 = Folder(name="F1", owner_id=u.id, parent_id=root.id)
        db.session.add(f1)
        db.session.flush()
        f2 = Folder(name="F2", owner_id=u.id, parent_id=f1.id)
        db.session.add(f2)
        db.session.commit()
        f2_uuid = f2.uuid

    response = client.get(f"/api/v1/folders/{f2_uuid}/path", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 3 # Root, F1, F2
    assert data[0]["is_root"] is True
    assert data[1]["name"] == "F1"
    assert data[2]["name"] == "F2"
    assert "uuid" in data[0]

def test_api_search_starred_recent(client, api_auth, app):
    user_id, token, _ = api_auth
    with app.app_context():
        u = db.session.get(User, user_id)
        root = Folder.query.filter_by(owner_id=u.id, is_root=True).first()
        f1 = File(owner_id=u.id, folder_id=root.id, original_filename="star.txt", stored_filename="s1.bin", size_bytes=10, sha256_hash="h1", storage_path="p1", is_starred=True)
        f2 = File(owner_id=u.id, folder_id=root.id, original_filename="recent.txt", stored_filename="s2.bin", size_bytes=10, sha256_hash="h2", storage_path="p2")
        db.session.add_all([f1, f2])
        db.session.commit()

    # Test Starred
    response = client.get("/api/v1/starred", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "star.txt"

    # Test Recent
    response = client.get("/api/v1/recent", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) >= 2
    assert data[0]["name"] == "recent.txt" # Ordered by updated_at desc

    # Test Search
    response = client.get("/api/v1/search?q=star", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "star.txt"


def test_api_search_includes_thumbnail_metadata(client, api_auth, app):
    user_id, token, _ = api_auth
    with app.app_context():
        u = db.session.get(User, user_id)
        root = Folder.query.filter_by(owner_id=u.id, is_root=True).first()
        image = File(
            owner_id=u.id,
            folder_id=root.id,
            original_filename="photo.png",
            stored_filename="photo.bin",
            mime_type="image/png",
            size_bytes=10,
            sha256_hash="h-photo",
            storage_path="files/ph/ot/photo.bin",
            preview_metadata={
                "thumbnail_status": "ready",
                "thumbnails": {
                    "small": "thumbnails/ph/ot/photo-small.webp",
                    "medium": "thumbnails/ph/ot/photo-medium.webp",
                    "large": "thumbnails/ph/ot/photo-large.webp",
                },
            },
        )
        db.session.add(image)
        db.session.commit()

    response = client.get("/api/v1/search?type=image/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    item = response.get_json()["data"]["items"][0]
    assert item["name"] == "photo.png"
    assert item["thumbnail_status"] == "ready"
    assert item["thumbnail_small_url"].endswith(f"/api/v1/files/{item['uuid']}/thumbnail?size=small")
    assert item["thumbnail_medium_url"].endswith(f"/api/v1/files/{item['uuid']}/thumbnail?size=medium")
    assert item["thumbnail_large_url"].endswith(f"/api/v1/files/{item['uuid']}/thumbnail?size=large")

def test_api_share_workflow(client, api_auth, app):
    user1_id, token1, _ = api_auth
    with app.app_context():
        user2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        u1 = db.session.get(User, user1_id)
        root1 = Folder.query.filter_by(owner_id=u1.id, is_root=True).first()
        f1 = File(owner_id=u1.id, folder_id=root1.id, original_filename="share_me.txt", stored_filename="s1.bin", size_bytes=10, sha256_hash="h1", storage_path="p1")
        db.session.add(f1)
        db.session.commit()
        file_uuid = f1.uuid

    # Share file with user2
    response = client.post("/api/v1/share", headers={"Authorization": f"Bearer {token1}"}, json={
        "resource_type": "file",
        "resource_uuid": file_uuid,
        "username": "user2",
        "permission": "viewer"
    })
    assert response.status_code == 201
    share_uuid = response.get_json()["data"]["uuid"]

    # List shares
    response = client.get(f"/api/v1/shares?resource_type=file&resource_uuid={file_uuid}", headers={"Authorization": f"Bearer {token1}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data) == 1
    assert data[0]["username"] == "user2"

    # Remove share
    response = client.delete(f"/api/v1/share/{share_uuid}", headers={"Authorization": f"Bearer {token1}"})
    assert response.status_code == 200

def test_api_trash_lifecycle(client, api_auth, app):
    user_id, token, _ = api_auth
    with app.app_context():
        u = db.session.get(User, user_id)
        root = Folder.query.filter_by(owner_id=u.id, is_root=True).first()
        f1 = Folder(name="TrashMe", owner_id=u.id, parent_id=root.id)
        db.session.add(f1)
        db.session.commit()
        folder_uuid = f1.uuid

    # Soft delete
    response = client.delete(f"/api/v1/folders/{folder_uuid}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    # Get trash
    response = client.get("/api/v1/trash", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert any(item["uuid"] == folder_uuid for item in data)

    # Restore
    response = client.post(f"/api/v1/folders/{folder_uuid}/restore", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    # Verify not in trash
    response = client.get("/api/v1/trash", headers={"Authorization": f"Bearer {token}"})
    assert len(response.get_json()["data"]) == 0

    # Permanent delete
    client.delete(f"/api/v1/folders/{folder_uuid}", headers={"Authorization": f"Bearer {token}"})
    response = client.delete(f"/api/v1/folders/{folder_uuid}?permanent=true", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_api_sync_changes(client, api_auth, app):
    user_id, token, _ = api_auth

    # Get initial changes
    response = client.get("/api/v1/sync/changes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    initial_data = response.get_json()["data"]
    cursor = initial_data["next_cursor"]

    # Create a folder
    client.post("/api/v1/folders", headers={"Authorization": f"Bearer {token}"}, json={"name": "SyncTest"})

    # Get incremental changes
    response = client.get(f"/api/v1/sync/changes?cursor={cursor}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["changes"]) >= 1
    assert data["changes"][0]["action"] == "created"
