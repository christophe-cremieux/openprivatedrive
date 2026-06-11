"""
Description: Pytest module covering bulk upload.
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
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_bulk"
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
        user = auth_service.create_user("bulkuser", "bulk@example.com", "password")
        user_id = user.id
    with client.session_transaction() as sess:
        sess['_user_id'] = user_id
        sess['_fresh'] = True
    return client, user_id

def test_single_file_custom_name(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': (io.BytesIO(b"single file"), 'test.txt'),
        'custom_name': 'renamed.txt',
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert File.query.filter_by(original_filename="renamed.txt").first() is not None
        assert File.query.filter_by(original_filename="test.txt").first() is None

def test_bulk_upload_sequential_rename(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': [
            (io.BytesIO(b"file 1"), 'a.jpg'),
            (io.BytesIO(b"file 2"), 'b.jpg')
        ],
        'prefix': 'holiday',
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"Successfully uploaded 2 files" in response.data

    with app.app_context():
        assert File.query.filter_by(original_filename="holiday_001.jpg").first() is not None
        assert File.query.filter_by(original_filename="holiday_002.jpg").first() is not None

def test_directory_upload_structure(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root = folder_service.get_user_root_folder(user)
        root_uuid = root.uuid

    data = {
        'file': [
            (io.BytesIO(b"nested 1"), 'file1.txt'),
            (io.BytesIO(b"nested 2"), 'file2.txt')
        ],
        'relative_paths[]': [
            'folder1/sub1/file1.txt',
            'folder1/file2.txt'
        ],
        'folder_uuid': root_uuid
    }
    response = client.post("/upload", data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        # Check folder structure
        f1 = Folder.query.filter_by(name='folder1', owner_id=user_id).first()
        assert f1 is not None

        s1 = Folder.query.filter_by(name='sub1', parent_id=f1.id).first()
        assert s1 is not None

        # Check files
        file1 = File.query.filter_by(original_filename='file1.txt', folder_id=s1.id).first()
        assert file1 is not None

        file2 = File.query.filter_by(original_filename='file2.txt', folder_id=f1.id).first()
        assert file2 is not None
