"""
Description: Pytest module covering activity log.
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
from app.models.activity_log import ActivityLog
from app.services.activity_log_service import activity_log_service
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.sharing.services import sharing_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_activity"
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

def test_activity_logging_actions(app, client):
    with app.app_context():
        # 1. Login/Failed Login
        u = auth_service.create_user("loguser", "l@ex.com", "pass")

        # Simulate login via client
        client.post('/login', data={'username': 'loguser', 'password': 'pass'}, follow_redirects=True)
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='login').count() == 1

        client.get('/logout', follow_redirects=True)

        client.post('/login', data={'username': 'loguser', 'password': 'wrong'}, follow_redirects=True)
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='failed_login').count() == 1

        # 2. Folder Actions
        root = folder_service.get_user_root_folder(u)
        # Root folder creation is logged in AuthService.create_user calling FolderService
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='create_folder', resource_type='folder', resource_id=root.id).count() == 1

        sub = folder_service.create_folder(u, root, "Sub")
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='create_folder', resource_id=sub.id).count() == 1

        # 3. Upload/Download Actions
        f1 = upload_service.process_upload(u, root, b"hello", "test.txt")
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='upload_file', resource_id=f1.id).count() == 1

        # Log in again to download as 'u'
        client.post('/login', data={'username': 'loguser', 'password': 'pass'}, follow_redirects=True)
        client.get(f'/files/{f1.uuid}/download')
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='download_file', resource_id=f1.id).count() == 1

        # 4. Sharing Actions
        u2 = auth_service.create_user("u2", "u2@ex.com", "pass")
        sharing_service.share_resource(u, f1, "u2", "viewer")
        assert ActivityLog.query.filter_by(actor_user_id=u.id, action='share_file', resource_id=f1.id).count() == 1

def test_activity_log_service_queries(app):
    with app.app_context():
        u = auth_service.create_user("queryuser", "q@ex.com", "pass")
        root = folder_service.get_user_root_folder(u)
        upload_service.process_upload(u, root, b"content", "file.txt")

        stats = activity_log_service.get_all_users_with_stats()
        user_stat = next(s for s in stats if s['user'].username == "queryuser")
        assert user_stat['storage_usage_bytes'] == 7

        sys_stats = activity_log_service.get_system_storage_usage()
        assert sys_stats['total_usage_bytes'] >= 7
        assert sys_stats['total_files'] >= 1
