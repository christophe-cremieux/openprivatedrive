"""
Description: Pytest module covering permission audit.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.drive.permissions import can_access, OWNER, MANAGER, EDITOR, VIEWER, NONE
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.models.share import Share
from app.extensions import db
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.sharing.services import sharing_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_perm_audit"
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

def test_permission_matrix(app):
    with app.app_context():
        owner = auth_service.create_user("owner", "o@ex.com", "pass")
        manager = auth_service.create_user("manager", "m@ex.com", "pass")
        editor = auth_service.create_user("editor", "e@ex.com", "pass")
        viewer = auth_service.create_user("viewer", "v@ex.com", "pass")
        other = auth_service.create_user("other", "oth@ex.com", "pass")
        admin = auth_service.create_user("admin_user", "a@ex.com", "pass")
        admin.is_admin = True
        db.session.commit()

        root = folder_service.get_user_root_folder(owner)
        folder = folder_service.create_folder(owner, root, "Shared Folder")
        file = File(
            uuid="test-file",
            owner_id=owner.id,
            folder_id=folder.id,
            original_filename="test.txt",
            stored_filename="test-file.bin",
            size_bytes=0,
            sha256_hash="fake",
            storage_path="test/path"
        )
        db.session.add(file)
        db.session.commit()

        sharing_service.share_resource(owner, folder, manager.username, MANAGER)
        sharing_service.share_resource(owner, folder, editor.username, EDITOR)
        sharing_service.share_resource(owner, folder, viewer.username, VIEWER)

        # Actions to test
        actions = ['view', 'download', 'upload', 'rename', 'move', 'delete', 'share']

        users = [
            (owner, "OWNER", True),
            (admin, "ADMIN", True),
            (manager, "MANAGER", {a: True for a in actions}),
            (editor, "EDITOR", {'view': True, 'download': True, 'upload': True, 'rename': True, 'move': False, 'delete': False, 'share': False}),
            (viewer, "VIEWER", {'view': True, 'download': True, 'upload': False, 'rename': False, 'move': False, 'delete': False, 'share': False}),
            (other, "OTHER", False)
        ]

        for user, role, expected in users:
            for action in actions:
                if isinstance(expected, bool):
                    exp = expected
                else:
                    exp = expected.get(action, False)

                assert can_access(user, folder, action) == exp, f"Folder action {action} failed for {role}"
                assert can_access(user, file, action) == exp, f"File action {action} failed for {role}"

def test_quarantine_permission(app):
    with app.app_context():
        owner = auth_service.create_user("owner2", "o2@ex.com", "pass")
        admin = auth_service.create_user("admin2", "a2@ex.com", "pass")
        admin.is_admin = True
        db.session.commit()

        file = File(
            uuid="quarantine-file",
            owner_id=owner.id,
            original_filename="virus.txt",
            stored_filename="virus.bin",
            size_bytes=0,
            sha256_hash="fake",
            storage_path="test/virus",
            is_quarantined=True
        )
        db.session.add(file)
        db.session.commit()

        # Owner cannot access quarantined file
        assert not can_access(owner, file, 'view')
        assert not can_access(owner, file, 'download')

        # Admin can access
        assert can_access(admin, file, 'view')
        assert can_access(admin, file, 'download')
