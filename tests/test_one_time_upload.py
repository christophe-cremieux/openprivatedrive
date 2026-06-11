"""
Description: Pytest module covering one time upload.
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
import io
from app import create_app, db
from app.models.user import User
from app.models.folder import Folder
from app.models.public_link import PublicLink
from app.public_links.services import public_link_service

class TestOneTimeUpload(unittest.TestCase):
    def setUp(self):
        if not os.path.exists('instance'):
            os.makedirs('instance')

        self.app = create_app()
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['TESTING'] = True
        self.app.config['STORAGE_PATH'] = 'test_storage'
        self.app.config['WTF_CSRF_ENABLED'] = False
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

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.user.id)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if os.path.exists('test_storage'):
            shutil.rmtree('test_storage')

    def test_one_time_upload_link_deactivates_after_use(self):
        # 1. Create a one-time upload link
        raw_token, link = public_link_service.create_public_link(
            self.user, self.folder,
            password='linkpassword',
            one_time_password=True,
            link_type='upload'
        )
        self.assertTrue(link.is_active)
        self.assertTrue(link.one_time_password)

        # 2. Upload a file using the link
        data = {
            'password': 'linkpassword',
            'file': (io.BytesIO(b"content"), 'test.txt')
        }
        response = self.client.post(f'/public/upload/{raw_token}/process', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)

        # 3. Verify link is now inactive
        db.session.refresh(link)
        self.assertFalse(link.is_active)

        # 4. Try to use it again
        response2 = self.client.get(f'/public/upload/{raw_token}')
        self.assertEqual(response2.status_code, 404)

if __name__ == '__main__':
    unittest.main()
