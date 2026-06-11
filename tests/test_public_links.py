"""
Description: Pytest module covering public links.
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
from app.models.public_link import PublicLink
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.public_links.services import public_link_service
from app.auth.services import auth_service
from app.config import Config
from app import create_app
from datetime import datetime, timedelta, timezone
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_public"
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

def test_basic_public_link(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"public data", "public.txt")

        raw_token, link = public_link_service.create_public_link(u1, file1)

        # Verify token not stored raw
        assert raw_token not in link.token_hash

        # Retrieve by token
        retrieved_link = public_link_service.get_link_by_token(raw_token)
        assert retrieved_link is not None
        assert retrieved_link.id == link.id

def test_expired_public_link(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"expired", "expired.txt")

        # Create link that expired yesterday
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        raw_token, link = public_link_service.create_public_link(u1, file1, expires_at=past_date)

        assert public_link_service.get_link_by_token(raw_token) is None

def test_password_protected_link(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"secret", "secret.txt")

        raw_token, link = public_link_service.create_public_link(u1, file1, password="password123")

        assert link.password_required is True
        assert public_link_service.validate_password(link, "wrong") is False
        assert public_link_service.validate_password(link, "password123") is True

def test_one_time_link(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"once", "once.txt")

        # One-time download (max_downloads=1)
        raw_token, link = public_link_service.create_public_link(u1, file1, max_downloads=1)

        public_link_service.increment_download_count(link)
        assert link.download_count == 1
        assert link.is_active is False
        assert public_link_service.get_link_by_token(raw_token) is None

def test_max_downloads_enforcement(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"limited", "limit.txt")

        raw_token, link = public_link_service.create_public_link(u1, file1, max_downloads=2)

        public_link_service.increment_download_count(link)
        assert public_link_service.get_link_by_token(raw_token) is not None

        public_link_service.increment_download_count(link)
        # It was active after 1st download, now count is 2.
        # get_link_by_token checks if download_count < max_downloads
        assert public_link_service.get_link_by_token(raw_token) is None

def test_public_upload_transaction(app):
    """Test the transactional logic and rollback behavior for public uploads."""
    from io import BytesIO
    from werkzeug.datastructures import FileStorage

    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        folder1 = folder_service.create_folder(u1, None, "Public Folder")

        raw_token, link = public_link_service.create_public_link(
            u1, folder1, password="pass", link_type="upload", max_files=1
        )

        # Test 1: Successful upload
        file1 = FileStorage(stream=BytesIO(b"file1 data"), filename="file1.txt")
        public_link_service.handle_public_upload_transaction(
            link.id, [file1], folder1, u1, "127.0.0.1", 10
        )
        db.session.commit()

        db.session.refresh(link)
        assert link.upload_count == 1
        assert link.uploaded_bytes == 10
        assert File.query.filter_by(folder_id=folder1.id).count() == 1

        # Test 2: Failed upload (max_files exceeded) should rollback and NOT save file
        file2 = FileStorage(stream=BytesIO(b"file2 data"), filename="file2.txt")
        with pytest.raises(ValueError, match="Maximum 1 files allowed"):
             public_link_service.handle_public_upload_transaction(
                link.id, [file2], folder1, u1, "127.0.0.1", 10
            )
        db.session.rollback()

        db.session.refresh(link)
        assert link.upload_count == 1 # Still 1
        assert File.query.filter_by(folder_id=folder1.id).count() == 1 # Still 1

def test_public_upload_physical_cleanup(app):
    """Verifies that physical files are deleted if the DB transaction fails."""
    from io import BytesIO
    from werkzeug.datastructures import FileStorage
    from unittest.mock import patch
    from app.services.storage_service import storage_service

    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        folder1 = folder_service.create_folder(u1, None, "Public Folder")
        raw_token, link = public_link_service.create_public_link(u1, folder1, password="pass", link_type="upload")

        file1 = FileStorage(stream=BytesIO(b"data"), filename="cleanup_test.txt")

        # Force a failure in increment_download_count, which is called after upload_service.process_upload
        with patch('app.public_links.services.PublicLinkService.increment_download_count', side_effect=ValueError("Forced DB Error")):
            with pytest.raises(ValueError, match="Forced DB Error"):
                public_link_service.handle_public_upload_transaction(
                    link.id, [file1], folder1, u1, "127.0.0.1", 4
                )

        # Verify no file in DB
        assert File.query.count() == 0

        # Verify NO file in storage (Best effort, as it should have been deleted)
        # We need to know what the path would have been. upload_service.process_upload uses uuid.uuid4()
        # Let's mock uuid.uuid4() to have a predictable path
        with patch('uuid.uuid4', return_value='fixed-uuid'):
            file2 = FileStorage(stream=BytesIO(b"data"), filename="cleanup_test_2.txt")
            with patch('app.public_links.services.PublicLinkService.increment_download_count', side_effect=ValueError("Forced DB Error")):
                with pytest.raises(ValueError, match="Forced DB Error"):
                    public_link_service.handle_public_upload_transaction(
                        link.id, [file2], folder1, u1, "127.0.0.1", 4
                    )

            # The path would be generated from 'fixed-uuid'
            rel_path = storage_service.generate_storage_path('fixed-uuid')
            full_path = storage_service.get_full_path(rel_path)
            assert not os.path.exists(full_path)
