"""
Description: Pytest module covering admin dashboard.
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
from app.auth.services import auth_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_admin"
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

@pytest.fixture
def client(app):
    return app.test_client()

def test_admin_dashboard_access(app, client):
    with app.app_context():
        admin = auth_service.create_user("admin_user", "admin@ex.com", "pass")
        admin.is_admin = True
        db.session.commit()

        user = auth_service.create_user("normal_user", "user@ex.com", "pass")

    # 1. Anonymous access -> redirect to login (Flask-Login)
    response = client.get('/admin/users')
    assert response.status_code == 302

    # 2. Non-admin access -> 403
    client.post('/login', data={'username': 'normal_user', 'password': 'pass'}, follow_redirects=True)
    response = client.get('/admin/users')
    assert response.status_code == 403

    client.get('/logout')

    # 3. Admin access -> 200
    client.post('/login', data={'username': 'admin_user', 'password': 'pass'}, follow_redirects=True)

    for path in ['/admin/users', '/admin/logs', '/admin/storage']:
        response = client.get(path)
        assert response.status_code == 200
        assert b"Admin" in response.data or b"Management" in response.data or b"Overview" in response.data
