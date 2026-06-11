"""
Description: Pytest module covering large uploads.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import io
import os
import hashlib
from app.extensions import db
from app.models.user import User
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.services.upload_session_service import upload_session_service
from app.auth.services import auth_service
from app import create_app
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_large_uploads"

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

def test_chunked_upload_session(app):
    with app.app_context():
        u = auth_service.create_user("u", "u@e.com", "pass")
        root = folder_service.get_user_root_folder(u)

        filename = "large.docx"
        chunk1 = b"0" * 1024 * 1024 # 1MB
        chunk2 = b"1" * 1024 * 1024 # 1MB
        total_size = len(chunk1) + len(chunk2)
        full_content = chunk1 + chunk2
        expected_hash = hashlib.sha256(full_content).hexdigest()

        # 1. Create session
        session = upload_session_service.create_session(
            u, filename, total_size, total_chunks=2, sha256_hash=expected_hash, folder_uuid=root.uuid
        )
        assert session.uuid is not None

        # 2. Upload chunks
        upload_session_service.save_chunk(session, 0, chunk1)
        upload_session_service.save_chunk(session, 1, chunk2)

        # 3. Finalize
        f = upload_session_service.finalize_session(session, u)
        assert f.original_filename == filename
        assert f.size_bytes == total_size
        assert f.sha256_hash == expected_hash

        # 4. Verify physical storage
        from app.services.storage_service import storage_service
        full_path = storage_service.get_full_path(f.storage_path)
        with open(full_path, 'rb') as phys_file:
            assert phys_file.read() == full_content

def test_bulk_directory_upload(app):
    with app.app_context():
        u = auth_service.create_user("u", "u@e.com", "pass")
        root = folder_service.get_user_root_folder(u)

        # Simulate directory upload: /Photos/Summer/img1.jpg, /Photos/img2.jpg
        file1 = io.BytesIO(b"data1")
        file1.filename = "img1.jpg"
        file2 = io.BytesIO(b"data2")
        file2.filename = "img2.jpg"

        files = [file1, file2]
        relative_paths = ["Photos/Summer/img1.jpg", "Photos/img2.jpg"]

        uploaded, errors = upload_service.process_bulk_upload(u, root, files, relative_paths=relative_paths)
        assert len(uploaded) == 2
        assert len(errors) == 0

        # Verify structure
        from app.models.folder import Folder
        photos = Folder.query.filter_by(parent_id=root.id, name="Photos").first()
        assert photos is not None
        summer = Folder.query.filter_by(parent_id=photos.id, name="Summer").first()
        assert summer is not None

        assert uploaded[0].folder_id == summer.id
        assert uploaded[1].folder_id == photos.id
