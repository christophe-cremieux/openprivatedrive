"""
Description: Pytest module covering file crud ui.
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
from app.extensions import db
from app.models.file import File
from app.models.user import User
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.auth.services import auth_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_file_crud"
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
def authenticated_user(app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")
        return user.id

def login_client(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = user_id
        sess['_fresh'] = True

def test_file_download(client, app, authenticated_user):
    login_client(client, authenticated_user)
    with app.app_context():
        user = db.session.get(User, authenticated_user)
        root = folder_service.get_user_root_folder(user)
        file_record = upload_service.process_upload(
            user, root, io.BytesIO(b"test data"), "test.txt"
        )
        file_uuid = file_record.uuid

    response = client.get(f"/files/{file_uuid}/download")
    assert response.status_code == 200
    assert response.data == b"test data"
    assert response.headers["Content-Disposition"] == "attachment; filename=test.txt"

def test_file_rename(client, app, authenticated_user):
    login_client(client, authenticated_user)
    with app.app_context():
        user = db.session.get(User, authenticated_user)
        root = folder_service.get_user_root_folder(user)
        file_record = upload_service.process_upload(
            user, root, io.BytesIO(b"test"), "old.txt"
        )
        file_uuid = file_record.uuid

    response = client.post(f"/files/{file_uuid}/rename", data={"name": "new.txt"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"new.txt" in response.data

    with app.app_context():
        updated_file = File.query.filter_by(uuid=file_uuid).first()
        assert updated_file.original_filename == "new.txt"

def test_file_delete(client, app, authenticated_user):
    login_client(client, authenticated_user)
    with app.app_context():
        user = db.session.get(User, authenticated_user)
        root = folder_service.get_user_root_folder(user)
        file_record = upload_service.process_upload(
            user, root, io.BytesIO(b"test"), "delete_me.txt"
        )
        file_uuid = file_record.uuid

    response = client.post(f"/files/{file_uuid}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"deleted successfully" in response.data

    with app.app_context():
        deleted_file = File.query.filter_by(uuid=file_uuid).first()
        assert deleted_file.is_deleted is True

def test_unauthorized_download(client, app):
    with app.app_context():
        user1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        user2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        root2 = folder_service.get_user_root_folder(user2)
        file2 = upload_service.process_upload(user2, root2, io.BytesIO(b"secret"), "secret.txt")
        file2_uuid = file2.uuid
        user1_id = user1.id

    login_client(client, user1_id)
    response = client.get(f"/files/{file2_uuid}/download")
    assert response.status_code == 403
