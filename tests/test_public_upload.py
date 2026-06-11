"""
Description: Pytest module covering public upload.
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
from app.services.folder_service import folder_service
from app.public_links.services import public_link_service
from app.auth.services import auth_service
from app.models.file import File
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_pub_upload"
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

def test_public_upload_flow(app, client):
    with app.app_context():
        user = auth_service.create_user("testuser", "t@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "Upload Target")
        folder_id = folder.id
        user_id = user.id

        # Create upload link
        raw_token, link = public_link_service.create_public_link(
            user, folder, password="upload_key", link_type="upload", max_files=2, max_upload_size_mb=1
        )

    # 1. View link without password
    response = client.get(f"/public/upload/{raw_token}")
    assert response.status_code == 200
    assert b"One-Time Key" in response.data

    # 2. View link with password
    response = client.post(f"/public/upload/{raw_token}", data={"password": "upload_key"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Ready to Upload" in response.data

    # 3. Perform upload
    data = {
        'password': 'upload_key',
        'file': (io.BytesIO(b"public upload content"), "public.txt")
    }
    response = client.post(f"/public/upload/{raw_token}/process", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"Upload Successful" in response.data

    # 4. Verify file in DB
    with app.app_context():
        uploaded_file = File.query.filter_by(original_filename="public.txt").first()
        assert uploaded_file is not None
        assert uploaded_file.folder_id == folder_id
        assert uploaded_file.owner_id == user_id

def test_public_upload_limits(app, client):
    with app.app_context():
        user = auth_service.create_user("limituser", "l@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "Limit Target")

        # Max 1 file
        raw_token, link = public_link_service.create_public_link(
            user, folder, password="key", link_type="upload", max_files=1
        )

    # Attempt to upload 2 files
    data = {
        'password': 'key',
        'file': [
            (io.BytesIO(b"f1"), "f1.txt"),
            (io.BytesIO(b"f2"), "f2.txt")
        ]
    }
    response = client.post(f"/public/upload/{raw_token}/process", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"Maximum 1 files allowed" in response.data

def test_public_upload_reject_encryption(app, client):
    with app.app_context():
        user = auth_service.create_user("encuser", "e@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "Enc Target")

        raw_token, link = public_link_service.create_public_link(
            user, folder, password="key", link_type="upload"
        )

    data = {
        'password': 'key',
        'file': (io.BytesIO(b"content"), "f1.txt"),
        'is_encrypted': 'true'
    }
    response = client.post(f"/public/upload/{raw_token}/process", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"Encryption is not supported for public uploads" in response.data

def test_public_upload_max_mb(app, client):
    with app.app_context():
        user = auth_service.create_user("mbuser", "mb@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "MB Target")

        # Max 1MB
        raw_token, link = public_link_service.create_public_link(
            user, folder, password="key", link_type="upload", max_upload_size_mb=1
        )

    # Attempt to upload 2MB
    big_file = io.BytesIO(b"0" * (2 * 1024 * 1024))
    data = {
        'password': 'key',
        'file': (big_file, "big.txt")
    }
    response = client.post(f"/public/upload/{raw_token}/process", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"Maximum total upload size per request is 1 MB" in response.data

def test_public_upload_expired(app, client):
    from datetime import datetime, timedelta, timezone
    with app.app_context():
        user = auth_service.create_user("expuser", "exp@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "Exp Target")

        # Expired link
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        raw_token, link = public_link_service.create_public_link(
            user, folder, password="key", link_type="upload", expires_at=expires_at
        )

    response = client.get(f"/public/upload/{raw_token}")
    assert response.status_code == 404
