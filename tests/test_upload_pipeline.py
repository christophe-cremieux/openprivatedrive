"""
Description: Pytest module covering upload pipeline.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import io
import pytest
import os
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.file import File
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_upload"
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
def authenticated_client(client, app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")
        user_id = user.id
    with client.session_transaction() as sess:
        sess['_user_id'] = user_id
        sess['_fresh'] = True
    return client, user_id

def test_successful_upload(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': (io.BytesIO(b"test content"), 'test.txt'),
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)

    assert response.status_code == 200
    assert b"uploaded successfully" in response.data

    with app.app_context():
        file_record = File.query.filter_by(original_filename="test.txt").first()
        assert file_record is not None
        assert file_record.owner_id == user_id
        assert file_record.size_bytes == 12

def test_blocked_extension_upload(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': (io.BytesIO(b"<?php echo 'hacked'; ?>"), 'malicious.php'),
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b"is blocked for security reasons" in response.data
    with app.app_context():
        assert File.query.filter_by(original_filename="malicious.php").first() is None

def test_quota_enforcement(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        # Set a very small quota: 10 bytes
        user.storage_quota_bytes = 10
        db.session.commit()
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': (io.BytesIO(b"this is more than 10 bytes"), 'large.txt'),
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)

    assert b"Storage quota exceeded" in response.data
    with app.app_context():
        assert File.query.filter_by(original_filename="large.txt").first() is None
