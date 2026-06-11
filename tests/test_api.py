"""
Description: Pytest module covering api.
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
    STORAGE_PATH = "/tmp/test_storage_api"
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
        token_data = api_service.create_tokens(user, "test_device", "Android Phone")
        return user, token_data['access_token'], token_data['refresh_token']

def test_api_login(client, app):
    with app.app_context():
        auth_service.create_user("loginuser", "login@ex.com", "password")

    response = client.post("/api/v1/auth/login", json={
        "username": "loginuser",
        "password": "password",
        "device_id": "dev1",
        "device_name": "Test Device"
    })
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert "expires_in" in data
    assert data["user"]["username"] == "loginuser"

def test_api_me(client, api_auth):
    user, access_token, _ = api_auth
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["username"] == "apiuser"

def test_api_refresh(client, api_auth):
    _, _, refresh_token = api_auth
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert "expires_in" in data

def test_api_invalid_token(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.get_json()["code"] == "invalid_token"

def test_api_folders_root(client, api_auth):
    user, access_token, _ = api_auth
    response = client.get("/api/v1/folders/root", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert response.get_json()["data"]["is_root"] is True

def test_api_create_folder(client, api_auth):
    user, access_token, _ = api_auth
    response = client.post("/api/v1/folders",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "API Folder"}
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["name"] == "API Folder"

def test_api_file_upload_download(client, api_auth):
    user, access_token, _ = api_auth

    # Upload
    response = client.post("/api/v1/files/upload",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"file": (io.BytesIO(b"api content"), "api.txt")},
        content_type='multipart/form-data'
    )
    assert response.status_code == 201
    file_uuid = response.get_json()["data"]["uuid"]

    # Download
    response = client.get(f"/api/v1/files/{file_uuid}/download",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.data == b"api content"

def test_api_permission_isolation(client, app, api_auth):
    user1, access_token1, _ = api_auth
    with app.app_context():
        user2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        root2 = Folder.query.filter_by(owner_id=user2.id, is_root=True).first()
        root2_uuid = root2.uuid

    # User 1 tries to access User 2's root folder
    response = client.get(f"/api/v1/folders/{root2_uuid}", headers={"Authorization": f"Bearer {access_token1}"})
    assert response.status_code == 403
