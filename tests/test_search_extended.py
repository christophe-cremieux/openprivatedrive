"""
Description: Pytest module covering search extended.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.models.file import File
from app.models.folder import Folder
from app.extensions import db
from app.auth.services import auth_service
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.config import Config
from app import create_app
import os

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_search_ext"
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

def test_search_functionality(app):
    with app.app_context():
        user = auth_service.create_user("searcher", "s@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)

        # Create folder
        folder = folder_service.create_folder(user, root, "Secret Documents")

        # Create files
        file1 = File(
            uuid="file1",
            owner_id=user.id,
            folder_id=root.id,
            original_filename="budget_2024.pdf",
            stored_filename="file1.bin",
            size_bytes=100,
            sha256_hash="hash1",
            storage_path="path1"
        )

        # File with extracted text
        file2 = File(
            uuid="file2",
            owner_id=user.id,
            folder_id=folder.id,
            original_filename="notes.txt",
            stored_filename="file2.bin",
            size_bytes=100,
            sha256_hash="hash2",
            storage_path="path2",
            preview_metadata={"extracted_text": "This is a secret meeting about the new project X."}
        )

        db.session.add(file1)
        db.session.add(file2)
        db.session.commit()

        # 1. Search by filename
        results = file_service.search_files(user, query="budget")
        assert len(results) == 1
        assert results[0].original_filename == "budget_2024.pdf"

        # 2. Search by folder name
        folders = folder_service.search_folders(user, query="Secret")
        assert len(folders) == 1
        assert folders[0].name == "Secret Documents"

        # 3. Search by extracted text
        results = file_service.search_files(user, query="project X")
        assert len(results) == 1
        assert results[0].original_filename == "notes.txt"

        # 4. Search encrypted file (should NOT find in text)
        file3 = File(
            uuid="file3",
            owner_id=user.id,
            folder_id=root.id,
            original_filename="enc.txt",
            stored_filename="file3.bin",
            size_bytes=100,
            sha256_hash="hash3",
            storage_path="path3",
            is_encrypted=True,
            preview_metadata={"extracted_text": "project X"} # Should be ignored
        )
        db.session.add(file3)
        db.session.commit()

        results = file_service.search_files(user, query="project X")
        assert len(results) == 1 # Still only notes.txt
