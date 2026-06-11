"""
Description: Pytest module covering admin reset.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import pytest
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.models.activity_log import ActivityLog
from app.services.admin_service import admin_service

def test_data_only_reset(app, db, temp_storage):
    """Test that data-only reset clears content but keeps users."""
    with app.app_context():
        # 1. Setup dummy data
        admin = User(username='admin_reset', email='admin_reset@example.com', password_hash='hash', is_admin=True)
        user2 = User(username='user2', email='user2@example.com', password_hash='hash')
        db.session.add(admin)
        db.session.add(user2)
        db.session.commit()

        folder = Folder(name='Test Folder', owner_id=admin.id)
        db.session.add(folder)
        db.session.commit()

        file = File(
            uuid='test-uuid',
            original_filename='test.txt',
            stored_filename='test.bin',
            owner_id=admin.id,
            folder_id=folder.id,
            size_bytes=10,
            sha256_hash='dummyhash',
            storage_path='files/te/st/test-uuid.bin'
        )
        db.session.add(file)
        db.session.commit()

        # Create dummy physical file
        storage_path = app.config['STORAGE_PATH']
        full_file_path = os.path.join(storage_path, 'files', 'te', 'st', 'test-uuid.bin')
        os.makedirs(os.path.dirname(full_file_path), exist_ok=True)
        with open(full_file_path, 'w') as f: f.write('dummy content')

        # Create activity log
        log = ActivityLog(actor_user_id=admin.id, action='test_action')
        db.session.add(log)
        db.session.commit()

        # 2. Perform Reset
        success, msg = admin_service.perform_system_reset(admin, mode='data_only')
        assert success is True

        # 3. Assertions
        assert User.query.count() == 2 # Admin and user2 should remain
        assert Folder.query.count() == 0
        assert File.query.count() == 0
        assert ActivityLog.query.count() == 0
        assert not os.path.exists(full_file_path)
        # Check subdirs re-created
        assert os.path.exists(os.path.join(storage_path, 'files'))

def test_full_factory_reset(app, db, temp_storage):
    """Test that full reset clears content and deletes other users."""
    with app.app_context():
        # 1. Setup dummy data
        admin = User(username='admin_full', email='admin_full@example.com', password_hash='hash', is_admin=True)
        user2 = User(username='user3', email='user3@example.com', password_hash='hash')
        db.session.add(admin)
        db.session.add(user2)
        db.session.commit()

        # 2. Perform Reset
        success, msg = admin_service.perform_system_reset(admin, mode='full')
        assert success is True

        # 3. Assertions
        assert User.query.count() == 1
        assert User.query.first().username == 'admin_full'
