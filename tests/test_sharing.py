"""
Description: Pytest module covering sharing.
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
from app.models.folder import Folder
from app.models.file import File
from app.models.share import Share
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.sharing.services import sharing_service
from app.auth.services import auth_service
from app.drive.permissions import can_access, VIEWER, EDITOR, MANAGER
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_sharing"
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

def test_file_sharing_permissions(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        u2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"content", "test.txt")

        # Initially u2 has no access
        assert can_access(u2, file1, 'view') is False

        # Share as viewer
        sharing_service.share_resource(u1, file1, u2.username, VIEWER)
        assert can_access(u2, file1, 'view') is True
        assert can_access(u2, file1, 'download') is True
        assert can_access(u2, file1, 'rename') is False

        # Upgrade to editor
        sharing_service.share_resource(u1, file1, u2.username, EDITOR)
        assert can_access(u2, file1, 'rename') is True
        assert can_access(u2, file1, 'delete') is False

        # Upgrade to manager
        sharing_service.share_resource(u1, file1, u2.username, MANAGER)
        assert can_access(u2, file1, 'delete') is True
        assert can_access(u2, file1, 'share') is True

def test_folder_sharing_inheritance(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        u2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        sub = folder_service.create_folder(u1, root1, "Subfolder")
        file_in_sub = upload_service.process_upload(u1, sub, b"sub content", "sub.txt")

        # Share parent folder with u2 as editor
        sharing_service.share_resource(u1, sub, u2.username, EDITOR, inherit=True)

        # u2 should have editor access to subfolder
        assert can_access(u2, sub, 'view') is True
        assert can_access(u2, sub, 'upload') is True

        # u2 should inherit editor access to file within subfolder
        assert can_access(u2, file_in_sub, 'view') is True
        assert can_access(u2, file_in_sub, 'rename') is True
        assert can_access(u2, file_in_sub, 'delete') is False

def test_unauthorized_sharing(app):
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        u2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        u3 = auth_service.create_user("user3", "u3@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)

        # u2 tries to share u1's root folder with u3
        with pytest.raises(ValueError, match="User does not have permission"):
            sharing_service.share_resource(u2, root1, u3.username, VIEWER)

def test_shared_with_me_ui(app):
    client = app.test_client()
    with app.app_context():
        u1 = auth_service.create_user("user1", "u1@ex.com", "pass")
        u2 = auth_service.create_user("user2", "u2@ex.com", "pass")
        root1 = folder_service.get_user_root_folder(u1)
        file1 = upload_service.process_upload(u1, root1, b"content", "shared_file.txt")
        sharing_service.share_resource(u1, file1, u2.username, VIEWER)
        u2_id = u2.id

    with client.session_transaction() as sess:
        sess['_user_id'] = u2_id
        sess['_fresh'] = True

    response = client.get("/shared-with-me")
    assert response.status_code == 200
    assert b"shared_file.txt" in response.data
    assert b"viewer" in response.data
    assert b"Shared by user1" in response.data
