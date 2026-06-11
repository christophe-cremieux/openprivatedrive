"""
Description: Pytest module covering auth.
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

def test_registration(client):
    response = client.post("/register", data={
        "username": "testuser",
        "email": "test@example.com",
        "password": "password",
        "password_confirm": "password"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Congratulations, you are now a registered user!" in response.data

    user = User.query.filter_by(username="testuser").first()
    assert user is not None
    assert user.email == "test@example.com"
    assert user.check_password("password")

def test_login_logout(client):
    # Register first
    client.post("/register", data={
        "username": "testuser",
        "email": "test@example.com",
        "password": "password",
        "password_confirm": "password"
    })

    # Login
    response = client.post("/login", data={
        "username": "testuser",
        "password": "password"
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome, testuser!" in response.data

    # Logout
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert b"Log In" in response.data
