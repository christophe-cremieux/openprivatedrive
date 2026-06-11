"""
Description: Pytest module covering file copy.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import unittest
import os
import shutil
from app import create_app, db
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.services.file_service import file_service
from app.services.storage_service import storage_service

class TestFileCopySemantics(unittest.TestCase):
    def setUp(self):
        # Ensure instance directory exists for app.db fallback even if we use :memory:
        # because of how extensions might be initialized.
        if not os.path.exists('instance'):
            os.makedirs('instance')

        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['TESTING'] = True
        self.app.config['STORAGE_PATH'] = 'test_storage'
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        if not os.path.exists('test_storage'):
            os.makedirs('test_storage')

        self.user = User(username='testuser', email='test@example.com')
        self.user.set_password('password')
        db.session.add(self.user)
        db.session.commit()

        self.folder = Folder(name='My Drive', owner_id=self.user.id, is_root=True)
        db.session.add(self.folder)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if os.path.exists('test_storage'):
            shutil.rmtree('test_storage')

    def test_copy_file_creates_new_physical_file(self):
        # 1. Create a file
        file_content = b"hello world"
        file_uuid = "original-uuid"
        rel_path = storage_service.backend.save(file_uuid, file_content)

        original_file = File(
            uuid=file_uuid,
            owner_id=self.user.id,
            folder_id=self.folder.id,
            original_filename="test.txt",
            stored_filename="test.txt",
            size_bytes=len(file_content),
            sha256_hash="hash",
            storage_path=rel_path
        )
        db.session.add(original_file)
        db.session.commit()

        # 2. Copy the file
        copied_file = file_service.copy_file(self.user, original_file, self.folder)

        # 3. Verify physical files are different
        self.assertNotEqual(original_file.storage_path, copied_file.storage_path)
        self.assertTrue(os.path.exists(storage_service.get_full_path(original_file.storage_path)))
        self.assertTrue(os.path.exists(storage_service.get_full_path(copied_file.storage_path)))

        # 4. Delete the copy permanently
        file_service.permanent_delete_file(self.user, copied_file)

        # 5. Verify original still exists
        self.assertTrue(os.path.exists(storage_service.get_full_path(original_file.storage_path)))
        self.assertFalse(os.path.exists(storage_service.get_full_path(copied_file.storage_path)))

if __name__ == '__main__':
    unittest.main()
