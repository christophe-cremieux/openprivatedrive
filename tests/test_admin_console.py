"""
Description: Pytest module covering admin console.
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
from app.models.system_stat import SystemStat
from app.services.antivirus_service import antivirus_service
from app.services.upload_policy_service import upload_policy_service
from app.services.upload_service import upload_service
from app.config import Config
from app import create_app
import os
import io

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_admin_console"
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

def test_admin_dashboard_v1_route(app, client):
    """Verifies that the new dashboard route is accessible to admins."""
    with app.app_context():
        admin = auth_service.create_user("admin_user", "admin@ex.com", "password123456")
        admin.is_admin = True
        db.session.commit()

    client.post('/login', data={'username': 'admin_user', 'password': 'password123456'}, follow_redirects=True)

    response = client.get('/admin/')
    assert response.status_code == 200
    assert b"Admin Dashboard" in response.data
    assert b"Total Users" in response.data
    assert b"Active Public Links" in response.data

def test_global_upload_limit_enforcement(app, client):
    """Verifies that the global upload limit in SystemStat is respected."""
    with app.app_context():
        admin = auth_service.create_user("admin_user", "admin@ex.com", "password123456")
        admin.is_admin = True

        # Set a small global limit: 1MB
        SystemStat.set_stat('global_max_upload_size_mb', 1)
        db.session.commit()

    client.post('/login', data={'username': 'admin_user', 'password': 'password123456'}, follow_redirects=True)

    # Attempt to upload a 2MB file
    large_data = b"0" * (2 * 1024 * 1024)
    response = client.post('/upload', data={
        'file': (io.BytesIO(large_data), 'test.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b"exceeds global upload limit" in response.data

    # Attempt to upload a 0.5MB file (should pass)
    small_data = b"0" * (512 * 1024)
    response = client.post('/upload', data={
        'file': (io.BytesIO(small_data), 'small.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert b"uploaded successfully" in response.data or response.status_code == 200

def test_capabilities_reports_effective_limit(app, client):
    """Verifies that /api/v1/capabilities reports the global limit if set."""
    with app.app_context():
        SystemStat.set_stat('global_max_upload_size_mb', 42)
        db.session.commit()

    response = client.get('/api/v1/capabilities')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['max_upload_size_mb'] == 42

def test_admin_can_toggle_antivirus_globally(app, client):
    with app.app_context():
        admin = auth_service.create_user("admin_user", "admin@ex.com", "password123456")
        admin.is_admin = True
        db.session.commit()

    client.post('/login', data={'username': 'admin_user', 'password': 'password123456'}, follow_redirects=True)

    response = client.post('/admin/upload-policy', data={
        'custom_allowed': '',
        'custom_blocked': '',
        'max_upload_size_mb': '0',
        'antivirus_enabled': 'on',
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        assert SystemStat.get_stat(antivirus_service.ENABLED_SETTING_KEY) is True

    response = client.post('/admin/upload-policy', data={
        'custom_allowed': '',
        'custom_blocked': '',
        'max_upload_size_mb': '0',
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        assert SystemStat.get_stat(antivirus_service.ENABLED_SETTING_KEY) is False

def test_admin_can_toggle_upload_policy_globally(app, client):
    with app.app_context():
        admin = auth_service.create_user("admin_user", "admin@ex.com", "password123456")
        admin.is_admin = True
        db.session.commit()

    client.post('/login', data={'username': 'admin_user', 'password': 'password123456'}, follow_redirects=True)

    response = client.post('/admin/upload-policy', data={
        'custom_allowed': '',
        'custom_blocked': '',
        'max_upload_size_mb': '0',
        'upload_policy_enabled': 'on',
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        assert SystemStat.get_stat(upload_policy_service.ENABLED_KEY) is True

    response = client.post('/admin/upload-policy', data={
        'custom_allowed': '',
        'custom_blocked': '',
        'max_upload_size_mb': '0',
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        assert SystemStat.get_stat(upload_policy_service.ENABLED_KEY) is False

def test_ready_endpoint_healthy(app, client):
    """Verifies that /ready returns 200 when DB and storage are available."""
    response = client.get('/ready')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ready'
    assert data['database'] == 'up'
    assert data['storage'] == 'writable'
