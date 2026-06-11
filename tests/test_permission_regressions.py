"""
Description: Pytest module covering permission regressions.
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
from app.sharing.services import sharing_service
from app.auth.services import auth_service
from app import create_app
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_permissions"

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_shared_folder_inheritance(app):
    with app.app_context():
        owner = auth_service.create_user("owner", "o@e.com", "pass")
        editor = auth_service.create_user("editor", "e@e.com", "pass")
        viewer = auth_service.create_user("viewer", "v@e.com", "pass")

        root = folder_service.get_user_root_folder(owner)
        parent = folder_service.create_folder(owner, root, "SharedParent")
        child = folder_service.create_folder(owner, parent, "SharedChild")
        file = File(owner_id=owner.id, folder_id=child.id, original_filename="doc.txt", stored_filename="s1.bin", size_bytes=10, sha256_hash="h1", storage_path="p1")
        db.session.add(file)
        db.session.commit()

        # Share Parent with Viewer as 'viewer'
        sharing_service.share_resource(owner, parent, "viewer", "viewer")

        # Verify Viewer can see Child and File
        assert folder_service.get_folder_by_uuid(child.uuid, user=viewer, action='view') is not None
        assert file_service.get_file_by_uuid(file.uuid, user=viewer, action='view') is not None

        # Verify Viewer CANNOT rename Child or File
        with pytest.raises(PermissionError):
            folder_service.rename_folder(viewer, child, "New Name")
        with pytest.raises(PermissionError):
            file_service.rename_file(viewer, file, "New Name")

        # Share Parent with Editor as 'editor'
        sharing_service.share_resource(owner, parent, "editor", "editor")

        # Verify Editor CAN rename Child and File
        folder_service.rename_folder(editor, child, "Renamed by Editor")
        file_service.rename_file(editor, file, "file_renamed.txt")
        assert child.name == "Renamed by Editor"
        assert file.original_filename == "file_renamed.txt"

def test_trash_access_restriction(app):
    with app.app_context():
        u = auth_service.create_user("u", "u@e.com", "pass")
        root = folder_service.get_user_root_folder(u)
        f = folder_service.create_folder(u, root, "TrashTest")
        f_uuid = f.uuid

        folder_service.soft_delete_folder(u, f)

        # Standard get_folder_by_uuid should return None (filtered out)
        assert folder_service.get_folder_by_uuid(f_uuid) is None

        # Owner can see it in direct query but service should block 'view' action for normal usage
        # Actually, get_folder_by_uuid has folder.is_deleted check.

        # Test that restoring requires ownership
        other = auth_service.create_user("other", "other@e.com", "pass")
        with pytest.raises(PermissionError):
            folder_service.restore_folder(other, f)

def test_move_permissions(app):
    with app.app_context():
        u1 = auth_service.create_user("u1", "u1@e.com", "pass")
        u2 = auth_service.create_user("u2", "u2@e.com", "pass")

        root1 = folder_service.get_user_root_folder(u1)
        root2 = folder_service.get_user_root_folder(u2)

        f1 = folder_service.create_folder(u1, root1, "F1")

        # u1 tries to move F1 to u2's root -> Should fail (no access to root2)
        with pytest.raises(PermissionError):
            folder_service.move_folder(u1, f1, root2)

        # u2 shared root2 with u1 as 'editor'
        sharing_service.share_resource(u2, root2, "u1", "editor")

        # Now u1 can move F1 to root2
        folder_service.move_folder(u1, f1, root2)
        assert f1.parent_id == root2.id
        # Note: Ownership remains u1.
