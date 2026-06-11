"""
Description: Pytest module covering upload directory verification.
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
from app.extensions import db
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.config import Config
from app import create_app

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_final"
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

def test_bulk_upload_from_provided_directory(app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password123456")
        root = folder_service.get_user_root_folder(user)

        upload_dir = "tests/test_upload"
        files_to_upload = [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]
        files_to_upload.sort()

        file_objs = []
        for filename in files_to_upload:
            with open(os.path.join(upload_dir, filename), 'rb') as f:
                content = f.read()
                file_obj = io.BytesIO(content)
                file_obj.filename = filename
                file_objs.append(file_obj)

        uploaded, errors = upload_service.process_bulk_upload(user, root, file_objs)

        assert len(uploaded) == len(files_to_upload)
        assert len(errors) == 0

        db_files = File.query.filter_by(owner_id=user.id).all()
        assert len(db_files) == len(files_to_upload)

def test_folder_upload_from_provided_directory(app):
    with app.app_context():
        user = auth_service.create_user("testuser2", "test2@example.com", "password123456")
        root = folder_service.get_user_root_folder(user)

        upload_dir = "tests/test_upload"
        files_to_upload = [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]
        files_to_upload.sort()

        file_objs = []
        relative_paths = []
        for filename in files_to_upload:
            with open(os.path.join(upload_dir, filename), 'rb') as f:
                content = f.read()
                file_obj = io.BytesIO(content)
                file_obj.filename = filename
                file_objs.append(file_obj)
                relative_paths.append(f"my_upload_folder/{filename}")

        uploaded, errors = upload_service.process_bulk_upload(user, root, file_objs, relative_paths=relative_paths)

        assert len(uploaded) == len(files_to_upload)
        assert len(errors) == 0

        folder = Folder.query.filter_by(name="my_upload_folder", parent_id=root.id).first()
        assert folder is not None

        db_files = File.query.filter_by(folder_id=folder.id).all()
        assert len(db_files) == len(files_to_upload)
