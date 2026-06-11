"""
Description: Pytest fixtures and shared testing utilities.
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
import shutil
import tempfile
from app import create_app
from app.extensions import db as _db
from app.models.user import User
from app.auth.services import auth_service
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    # Each test function will have its own STORAGE_PATH set by the fixture

@pytest.fixture(scope="session")
def app():
    """Session-wide test `Flask` application."""
    app = create_app(TestConfig)
    return app

@pytest.fixture
def temp_storage(app, monkeypatch):
    """Temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setitem(app.config, "STORAGE_PATH", temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def db(app):
    """Clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def test_user_factory(db):
    """Factory for creating test users."""
    def _create_user(username="testuser", email="test@example.com", password="password", is_admin=False):
        user = auth_service.create_user(username=username, email=email, password=password)
        if is_admin:
            user.is_admin = True
            db.session.commit()
        return user
    return _create_user

@pytest.fixture
def authenticated_client(client, test_user_factory):
    """Client authenticated as a test user."""
    user = test_user_factory(username="authuser", email="auth@example.com")
    client.post("/login", data={
        "username": "authuser",
        "password": "password"
    })
    return client, user

@pytest.fixture
def client(app):
    """A Flask test client."""
    return app.test_client()
