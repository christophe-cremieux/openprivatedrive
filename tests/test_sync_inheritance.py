"""
Description: Pytest module covering sync inheritance.
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
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.sharing.services import sharing_service
from app.auth.services import auth_service
from app.models.sync_event import SyncEvent
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_sync_inh"
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

def test_inherited_sync_event_visibility(app):
    with app.app_context():
        u1 = auth_service.create_user("u1_inh", "u1i@ex.com", "pass")
        u2 = auth_service.create_user("u2_inh", "u2i@ex.com", "pass")

        root1 = folder_service.get_user_root_folder(u1)
        sub = folder_service.create_folder(u1, root1, "Shared Parent")

        # Share folder with u2, with inheritance
        sharing_service.share_resource(u1, sub, u2.username, 'viewer', inherit=True)

        # Now u1 creates a file INSIDE the shared folder
        file1 = upload_service.process_upload(u1, sub, b"inherited sync", "inh.txt")

        # u2 should have a 'created' event for this file because of inheritance
        event = SyncEvent.query.filter_by(user_id=u2.id, resource_id=file1.id, action='created').first()
        assert event is not None, "u2 should see file creation event via inherited folder permission"
