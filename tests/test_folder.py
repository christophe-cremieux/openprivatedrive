"""
Description: Pytest module covering folder.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.folder import Folder
from app.services.folder_service import folder_service
from app.auth.services import auth_service
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_root_folder_creation_on_registration(app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")

        root_folder = folder_service.get_user_root_folder(user)
        assert root_folder is not None
        assert root_folder.name == "My Drive"
        assert root_folder.is_root is True
        assert root_folder.owner_id == user.id
        assert root_folder.parent_id is None

def test_create_subfolder(app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")
        root_folder = folder_service.get_user_root_folder(user)

        subfolder = folder_service.create_folder(user, root_folder, "Documents")
        assert subfolder is not None
        assert subfolder.name == "Documents"
        assert subfolder.owner_id == user.id
        assert subfolder.parent_id == root_folder.id
        assert subfolder.is_root is False

def test_user_separation(app):
    with app.app_context():
        user1 = auth_service.create_user("user1", "user1@example.com", "password")
        user2 = auth_service.create_user("user2", "user2@example.com", "password")

        root1 = folder_service.get_user_root_folder(user1)
        root2 = folder_service.get_user_root_folder(user2)

        assert root1.owner_id == user1.id
        assert root2.owner_id == user2.id
        assert root1.id != root2.id

from app.drive.permissions import can_access

def test_root_folder_protection(app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")
        root_folder = folder_service.get_user_root_folder(user)

        # User should be able to view their root folder
        assert can_access(user, root_folder, 'view') is True

        # User should be able to rename their root folder (logically they are owner)
        # Note: UI routes block rename/delete of root, but permission engine says owner can.
        assert can_access(user, root_folder, 'rename') is True

        # Admin should be able to edit anything
        admin = auth_service.create_user("adminuser", "admin@example.com", "password", is_admin=True)
        assert can_access(admin, root_folder, 'rename') is True

def test_user_access_permissions(app):
    with app.app_context():
        user1 = auth_service.create_user("user1", "user1@example.com", "password")
        user2 = auth_service.create_user("user2", "user2@example.com", "password")

        root1 = folder_service.get_user_root_folder(user1)
        root2 = folder_service.get_user_root_folder(user2)

        # user1 cannot view or edit user2's folder
        assert can_access(user1, root2, 'view') is False
        assert can_access(user1, root2, 'rename') is False
