"""
Description: Pytest module covering folder crud ui.
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
from flask import url_for

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'

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

@pytest.fixture
def authenticated_client(client, app):
    with app.app_context():
        user = auth_service.create_user("testuser", "test@example.com", "password")
        user_id = user.id

    with client.session_transaction() as sess:
        sess['_user_id'] = user_id
        sess['_fresh'] = True
    return client, user_id

def test_view_my_drive_redirect(authenticated_client):
    client, user_id = authenticated_client
    response = client.get("/my-drive", follow_redirects=True)
    assert response.status_code == 200
    # Since we are using dashboard.html which we just updated, let's check for its content
    assert b"New Folder" in response.data

def test_create_folder_ui(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root_folder = folder_service.get_user_root_folder(user)
        root_uuid = root_folder.uuid

    response = client.post("/folders/create", data={
        "name": "New Subfolder",
        "parent_uuid": root_uuid
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"New Subfolder" in response.data

    with app.app_context():
        subfolder = Folder.query.filter_by(name="New Subfolder").first()
        assert subfolder is not None
        assert subfolder.owner_id == user_id

def test_rename_folder_ui(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root_folder = folder_service.get_user_root_folder(user)
        subfolder = folder_service.create_folder(user, root_folder, "Old Name")
        subfolder_uuid = subfolder.uuid

    response = client.post(f"/folders/{subfolder_uuid}/rename", data={
        "name": "New Name"
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"New Name" in response.data

    with app.app_context():
        subfolder = Folder.query.filter_by(uuid=subfolder_uuid).first()
        assert subfolder.name == "New Name"

def test_delete_folder_ui(authenticated_client, app):
    client, user_id = authenticated_client
    with app.app_context():
        user = db.session.get(User, user_id)
        root_folder = folder_service.get_user_root_folder(user)
        subfolder = folder_service.create_folder(user, root_folder, "To Delete")
        subfolder_uuid = subfolder.uuid

    response = client.post(f"/folders/{subfolder_uuid}/delete", follow_redirects=True)

    assert response.status_code == 200
    # The message should contain the success flash
    assert b"deleted successfully" in response.data

    with app.app_context():
        subfolder = Folder.query.filter_by(uuid=subfolder_uuid).first()
        assert subfolder.is_deleted is True

def test_folder_isolation_ui(app, client):
    with app.app_context():
        user1 = auth_service.create_user("user1", "user1@example.com", "password")
        user2 = auth_service.create_user("user2", "user2@example.com", "password")
        root2 = folder_service.get_user_root_folder(user2)

        user1_id = user1.id
        root2_uuid = root2.uuid

    # Log in as user1
    with client.session_transaction() as sess:
        sess['_user_id'] = user1_id
        sess['_fresh'] = True

    # Try to view user2's root folder
    response = client.get(f"/folders/{root2_uuid}")
    assert response.status_code == 403

    # Try to rename user2's folder
    response = client.post(f"/folders/{root2_uuid}/rename", data={"name": "Hacked"})
    assert response.status_code == 403

    # Try to delete user2's folder
    response = client.post(f"/folders/{root2_uuid}/delete")
    assert response.status_code == 403
