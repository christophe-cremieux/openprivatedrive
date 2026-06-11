"""
Description: Pytest module covering harden and features.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import os
import io
import json
from app import create_app, db
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.services.folder_service import folder_service
from flask import url_for

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "STORAGE_PATH": "/tmp/test_storage_harden",
        "WTF_CSRF_ENABLED": False
    })

    if not os.path.exists(app.config["STORAGE_PATH"]):
        os.makedirs(app.config["STORAGE_PATH"])

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers(app, client):
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        # Create root folder
        folder_service.create_root_folder_for_user(user)
        db.session.commit()

        # Login to get token
        response = client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "password123",
            "device_id": "test_device"
        })
        token = response.get_json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

def test_capabilities_storage_info(app, client, auth_headers):
    # 1. Check capabilities without auth
    response = client.get("/api/v1/capabilities")
    data = response.get_json()["data"]
    assert data["storage_used_bytes"] == 0
    assert data["storage_limit_bytes"] == 0

    # 2. Add a file to storage usage
    with app.app_context():
        user = User.query.filter_by(username="testuser").first()
        root = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

        file_rec = File(
            uuid="test-uuid-1",
            owner_id=user.id,
            folder_id=root.id,
            original_filename="test.txt",
            stored_filename="test.bin",
            mime_type="text/plain",
            size_bytes=1024 * 1024, # 1MB
            storage_path="files/te/st/test.bin",
            sha256_hash="hash"
        )
        db.session.add(file_rec)
        db.session.commit()

    # 3. Check capabilities with auth
    response = client.get("/api/v1/capabilities", headers=auth_headers)
    data = response.get_json()["data"]
    assert data["storage_used_bytes"] == 1024 * 1024
    assert data["storage_limit_bytes"] == 5368709120 # Default 5GB

def test_storage_usage_page(app, client):
    with app.app_context():
        user = User(username="webuser", email="web@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        folder_service.create_root_folder_for_user(user)
        db.session.commit()

    client.post("/login", data={"username": "webuser", "password": "password123"}, follow_redirects=True)

    response = client.get("/storage-usage")
    assert response.status_code == 200
    assert b"Your Storage Overview" in response.data
    assert b"MB used" in response.data

def test_delete_redirect(app, client):
    with app.app_context():
        user = User(username="deluser", email="del@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        folder_service.create_root_folder_for_user(user)
        db.session.commit()

        root = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
        sub = Folder(name="sub", owner_id=user.id, parent_id=root.id)
        db.session.add(sub)
        db.session.commit()

        file_rec = File(
            uuid="del-file-uuid",
            owner_id=user.id,
            folder_id=sub.id,
            original_filename="delme.txt",
            stored_filename="delme.bin",
            mime_type="text/plain",
            size_bytes=100,
            storage_path="files/de/lm/delme.bin",
            sha256_hash="hash"
        )
        db.session.add(file_rec)
        db.session.commit()

        sub_uuid = sub.uuid

    client.post("/login", data={"username": "deluser", "password": "password123"}, follow_redirects=True)

    # Delete file and check redirect
    response = client.post(f"/files/del-file-uuid/delete", follow_redirects=False)
    assert response.status_code == 302
    assert f"/folders/{sub_uuid}" in response.location

def test_harden_decrypt_path_traversal(app, client, auth_headers):
    with app.app_context():
        user = User.query.filter_by(username="testuser").first()
        root = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

        # Malicious storage path
        file_rec = File(
            uuid="evil-uuid",
            owner_id=user.id,
            folder_id=root.id,
            original_filename="evil.txt",
            stored_filename="evil.bin",
            mime_type="text/plain",
            size_bytes=100,
            storage_path="../../../../etc/passwd",
            is_encrypted=True,
            sha256_hash="hash"
        )
        db.session.add(file_rec)
        db.session.commit()

    # API Attempt
    response = client.post("/api/v1/files/evil-uuid/decrypt-download",
                           json={"password": "password123456"},
                           headers=auth_headers)
    assert response.status_code == 403

    # Web Attempt
    client.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=True)
    response = client.post("/files/evil-uuid/decrypt", data={"password": "password123456"})
    assert response.status_code == 403
