"""
Description: Pytest module covering services extended.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.extensions import db
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.upload_service import upload_service
from app.auth.services import auth_service
from app import create_app
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_services"

@pytest.fixture
def app():
    app = create_app(TestConfig)
    import os
    if not os.path.exists(TestConfig.STORAGE_PATH):
        os.makedirs(TestConfig.STORAGE_PATH)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_move_file_collision(app):
    with app.app_context():
        u = auth_service.create_user(username="u", email="u@e.com", password="pass")

        root = folder_service.get_user_root_folder(u)
        f1 = folder_service.create_folder(u, root, "F1")
        f2 = folder_service.create_folder(u, root, "F2")

        file1 = File(owner_id=u.id, folder_id=f1.id, original_filename="test.txt", stored_filename="s1.bin", size_bytes=1, sha256_hash="h1", storage_path="p1")
        file2 = File(owner_id=u.id, folder_id=f2.id, original_filename="test.txt", stored_filename="s2.bin", size_bytes=1, sha256_hash="h2", storage_path="p2")
        db.session.add_all([file1, file2])
        db.session.commit()

        with pytest.raises(ValueError, match="already exists in the destination"):
            file_service.move_file(u, file1, f2)

def test_folder_cycle_prevention(app):
    with app.app_context():
        u = auth_service.create_user(username="u", email="u@e.com", password="pass")

        root = folder_service.get_user_root_folder(u)
        parent = folder_service.create_folder(u, root, "Parent")
        child = folder_service.create_folder(u, parent, "Child")

        with pytest.raises(ValueError, match="itself or one of its descendants"):
            folder_service.move_folder(u, parent, child)

def test_search_filters(app):
    with app.app_context():
        u = auth_service.create_user(username="u", email="u@e.com", password="pass")

        root = folder_service.get_user_root_folder(u)
        file1 = File(owner_id=u.id, folder_id=root.id, original_filename="apple.txt", stored_filename="apple.bin", mime_type="text/plain", size_bytes=1, sha256_hash="h1", storage_path="p1", is_starred=True)
        file2 = File(owner_id=u.id, folder_id=root.id, original_filename="banana.jpg", stored_filename="banana.bin", mime_type="image/jpeg", size_bytes=1, sha256_hash="h2", storage_path="p2")
        db.session.add_all([file1, file2])
        db.session.commit()

        results = file_service.search_files(u, query="apple")
        assert len(results) == 1
        assert results[0].original_filename == "apple.txt"

        results = file_service.search_files(u, mime_type="image/jpeg")
        assert len(results) == 1

        results = file_service.search_files(u, is_starred=True)
        assert len(results) == 1
        assert results[0].original_filename == "apple.txt"

def test_full_trash_lifecycle(app):
    with app.app_context():
        u = auth_service.create_user(username="u", email="u@e.com", password="pass")

        root = folder_service.get_user_root_folder(u)
        folder = folder_service.create_folder(u, root, "Trash Test")
        folder_id = folder.id

        # Soft delete
        folder_service.soft_delete_folder(u, folder)
        assert db.session.get(Folder, folder_id).is_deleted == True

        # Restore
        folder_service.restore_folder(u, folder)
        assert db.session.get(Folder, folder_id).is_deleted == False

        # Permanent
        folder_service.soft_delete_folder(u, folder)
        folder_service.permanent_delete_folder(u, folder)
        assert db.session.get(Folder, folder_id) is None

def test_metadata_extraction(app):
    with app.app_context():
        u = auth_service.create_user(username="u", email="u@e.com", password="pass")
        root = folder_service.get_user_root_folder(u)

        # Test text preview
        content = b"Hello world! This is a test file for metadata extraction."
        file_obj = io.BytesIO(content)
        file_obj.filename = "test.txt"

        f = upload_service.process_upload(u, root, file_obj)
        assert f.preview_metadata is not None
        assert f.preview_metadata['text_preview'] == "Hello world! This is a test file for metadata extraction."

def test_trash_retention_policy(app):
    from datetime import datetime, timezone, timedelta
    from app.services.background_jobs import trash_retention_policy_job

    with app.app_context():
        u = auth_service.create_user(username="retention_user", email="r@e.com", password="pass")
        root = folder_service.get_user_root_folder(u)

        # 1. Create a file and soft-delete it with an old date
        f1 = File(owner_id=u.id, folder_id=root.id, original_filename="old_deleted.txt", stored_filename="old.bin", size_bytes=10, sha256_hash="h1", storage_path="p1", is_deleted=True)
        # Manually set deleted_at to 31 days ago
        f1.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=31)
        db.session.add(f1)

        # 2. Create a file and soft-delete it recently
        f2 = File(owner_id=u.id, folder_id=root.id, original_filename="recent_deleted.txt", stored_filename="recent.bin", size_bytes=10, sha256_hash="h2", storage_path="p2", is_deleted=True)
        f2.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        db.session.add(f2)

        db.session.commit()

        f1_id = f1.id
        f2_id = f2.id

        # 3. Run retention job
        # We need to mock permanent_delete_file to avoid storage errors or just ensure storage exists
        # In this test environment, STORAGE_PATH is /tmp/... so it's fine.
        trash_retention_policy_job(app=app)

        # 4. Verify results
        db.session.expire_all()
        assert db.session.get(File, f1_id) is None # Deleted
        assert db.session.get(File, f2_id) is not None # Still there

import io
