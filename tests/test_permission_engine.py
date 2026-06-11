"""
Description: Pytest module covering permission engine.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.drive.permissions import can_access, OWNER, MANAGER, EDITOR, VIEWER, NONE, get_effective_permission
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.extensions import db
from app import create_app
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_ownership_permissions(app):
    with app.app_context():
        user = User(username="owner", email="owner@ex.com")
        user.set_password("pass")
        db.session.add(user)
        db.session.flush()

        folder = Folder(name="My Folder", owner_id=user.id)
        db.session.add(folder)
        db.session.flush()

        assert get_effective_permission(user, folder) == OWNER
        assert can_access(user, folder, 'view') is True
        assert can_access(user, folder, 'delete') is True
        assert can_access(user, folder, 'manage') is True

def test_unauthorized_access(app):
    with app.app_context():
        owner = User(username="owner", email="owner@ex.com")
        other = User(username="other", email="other@ex.com")
        for u in [owner, other]:
            u.set_password("pass")
            db.session.add(u)
        db.session.flush()

        folder = Folder(name="Owner Folder", owner_id=owner.id)
        db.session.add(folder)
        db.session.flush()

        assert get_effective_permission(other, folder) == NONE
        assert can_access(other, folder, 'view') is False
        assert can_access(other, folder, 'upload') is False

def test_soft_deleted_protection(app):
    with app.app_context():
        user = User(username="owner", email="owner@ex.com")
        user.set_password("pass")
        db.session.add(user)
        db.session.flush()

        folder = Folder(name="Deleted Folder", owner_id=user.id, is_deleted=True)
        db.session.add(folder)
        db.session.flush()

        # Even owner cannot access deleted resource via normal can_access
        assert can_access(user, folder, 'view') is False

def test_admin_permissions(app):
    with app.app_context():
        admin = User(username="admin", email="admin@ex.com", is_admin=True)
        user = User(username="user", email="user@ex.com")
        for u in [admin, user]:
            u.set_password("pass")
            db.session.add(u)
        db.session.flush()

        folder = Folder(name="User Folder", owner_id=user.id)
        db.session.add(folder)
        db.session.flush()

        assert get_effective_permission(admin, folder) == OWNER
        assert can_access(admin, folder, 'view') is True
        assert can_access(admin, folder, 'delete') is True

def test_permission_matrix_logic(app):
    # This test focuses on the logic inside can_access by mocking get_effective_permission
    import app.drive.permissions as permissions
    from unittest.mock import patch

    class MockResource:
        is_deleted = False

    mock_user = "user"
    mock_res = MockResource()

    with patch('app.drive.permissions.get_effective_permission') as mock_get_perm:
        # Test VIEWER
        mock_get_perm.return_value = VIEWER
        assert permissions.can_access(mock_user, mock_res, 'view') is True
        assert permissions.can_access(mock_user, mock_res, 'download') is True
        assert permissions.can_access(mock_user, mock_res, 'upload') is False

        # Test EDITOR
        mock_get_perm.return_value = EDITOR
        assert permissions.can_access(mock_user, mock_res, 'upload') is True
        assert permissions.can_access(mock_user, mock_res, 'rename') is True
        assert permissions.can_access(mock_user, mock_res, 'delete') is False

        # Test MANAGER
        mock_get_perm.return_value = MANAGER
        assert permissions.can_access(mock_user, mock_res, 'delete') is True
        assert permissions.can_access(mock_user, mock_res, 'share') is True
        assert permissions.can_access(mock_user, mock_res, 'manage') is False
