"""
Description: Pytest module covering storage.
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
import uuid
from app import create_app
from app.extensions import db
from app.services.storage_service import storage_service
from app.models.file import File
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage"

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
    # Cleanup storage after tests
    import shutil
    if os.path.exists(TestConfig.STORAGE_PATH):
        shutil.rmtree(TestConfig.STORAGE_PATH)

def test_storage_path_sharding(app):
    with app.app_context():
        file_uuid = str(uuid.uuid4())
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]

        rel_path = storage_service.generate_storage_path(file_uuid)
        expected_path = os.path.join("files", shard1, shard2, f"{file_uuid}.bin")
        assert rel_path == expected_path

def test_save_file(app):
    with app.app_context():
        file_uuid = str(uuid.uuid4())
        file_data = b"hello world"

        rel_path = storage_service.save_file(file_uuid, file_data)
        full_path = storage_service.get_full_path(rel_path)

        assert os.path.exists(full_path)
        with open(full_path, "rb") as f:
            assert f.read() == file_data

def test_file_model_creation(app):
    from app.models.user import User
    from app.models.folder import Folder
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.flush()

        folder = Folder(name="My Drive", owner_id=user.id, is_root=True)
        db.session.add(folder)
        db.session.flush()

        file_record = File(
            owner_id=user.id,
            folder_id=folder.id,
            original_filename="test.txt",
            stored_filename=f"{uuid.uuid4()}.bin",
            size_bytes=11,
            sha256_hash="abc",
            storage_path="files/ab/cd/ef.bin"
        )
        db.session.add(file_record)
        db.session.commit()

        saved_file = File.query.filter_by(original_filename="test.txt").first()
        assert saved_file is not None
        assert saved_file.owner_id == user.id
        assert saved_file.folder_id == folder.id
