"""
Description: Pytest module covering upload stats.
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
    STORAGE_PATH = "/tmp/test_storage_stats"
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

def test_upload_stat_tracking(app):
    with app.app_context():
        user = auth_service.create_user("statuser", "s@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        folder = folder_service.create_folder(user, root, "Upload Stat Target")

        # Create upload link
        raw_token, link = public_link_service.create_public_link(
            user, folder, password="key", link_type="upload"
        )

        assert link.upload_count == 0
        assert link.download_count == 0

        # Simulate upload (which calls increment_download_count)
        public_link_service.increment_download_count(link)

        assert link.upload_count == 1
        assert link.download_count == 0
        assert link.last_accessed_at is not None

def test_download_stat_tracking(app):
    with app.app_context():
        user = auth_service.create_user("dlstatuser", "dl@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)
        file = File(
            uuid="dl-file",
            owner_id=user.id,
            folder_id=root.id,
            original_filename="dl.txt",
            stored_filename="dl.bin",
            size_bytes=10,
            sha256_hash="fake",
            storage_path="path"
        )
        db.session.add(file)
        db.session.commit()

        # Create download link
        raw_token, link = public_link_service.create_public_link(
            user, file, link_type="download"
        )

        assert link.upload_count == 0
        assert link.download_count == 0

        # Simulate download
        public_link_service.increment_download_count(link)

        assert link.upload_count == 0
        assert link.download_count == 1
        assert link.last_accessed_at is not None
