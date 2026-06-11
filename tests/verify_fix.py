"""
Description: Pytest module covering verify fix.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import os
import zipfile
from app.models.file import File
from app.models.folder import Folder
from app.services.zip_service import zip_service
from app.extensions import db

def test_verify_zip_fix(app, db, test_user_factory):
    """Verify that the ZIP structure is flat and duplicates are handled."""
    user = test_user_factory()
    with app.app_context():
        # Setup: A folder and a file
        folder = Folder(name="black", owner_id=user.id)
        db.session.add(folder)
        db.session.commit()

        # Add a file to the folder
        file_in_folder = File(original_filename="inner.txt", folder_id=folder.id, owner_id=user.id, size_bytes=10,
                            storage_path="fake/inner.bin", stored_filename="inner.bin", sha256_hash="hash_inner")
        db.session.add(file_in_folder)

        file = File(original_filename="headphone.png", folder_id=None, owner_id=user.id, size_bytes=100,
                  storage_path="fake/h1.bin", stored_filename="h1.bin", sha256_hash="hash1")
        db.session.add(file)
        db.session.commit()

        # Mock storage_service and os.path.exists
        from unittest.mock import patch
        with patch('app.services.zip_service.storage_service.get_full_path', return_value="/tmp/fake.bin"), \
             patch('app.services.zip_service.os.path.exists', return_value=True), \
             patch('app.services.zip_service.can_access', return_value=True):

            # 1. Test ZIP structure (no "Selected items")
            files = [file]
            folders = [folder]
            zip_path = zip_service.create_zip_file(user, files, folders)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    namelist = zf.namelist()
                    print(f"ZIP namelist: {namelist}")

                    # Verify no "Selected items"
                    assert not any(name.startswith("Selected items/") for name in namelist)

                    # Verify flat structure for files
                    assert "headphone.png" in namelist
                    assert "black/inner.txt" in namelist
            finally:
                if os.path.exists(zip_path):
                    os.remove(zip_path)

            # 2. Test Duplicates (Backend handling)
            files = [file, file]
            folders = [folder, folder]
            zip_path = zip_service.create_zip_file(user, files, folders)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    namelist = zf.namelist()
                    print(f"ZIP namelist with duplicates: {namelist}")

                    # zip_service.create_zip_file itself doesn't de-duplicate, it relies on unique_arcname which adds suffixes
                    # So we expect headphone.png and headphone_1.png IF we pass them twice to create_zip_file.
                    # HOWEVER, our fix in routes_web.py de-duplicates them BEFORE calling create_zip_file.
                    # Let's test that routes_web.py logic works as intended (via integration or separate test).
                    # For THIS unit test of zip_service, it just confirms it still does the naming right.

                    assert "headphone.png" in namelist
                    assert "headphone_1.png" in namelist
                    assert "black/inner.txt" in namelist
                    assert "black_1/inner.txt" in namelist
            finally:
                if os.path.exists(zip_path):
                    os.remove(zip_path)

def test_verify_route_deduplication(app, db, test_user_factory):
    """Verify that the bulk_download route de-duplicates UUIDs."""
    user = test_user_factory()
    with app.test_request_context('/bulk/download?file_uuids[]=uuid1&file_uuids[]=uuid1'):
        from flask import request
        from flask_login import login_user
        from unittest.mock import MagicMock, patch

        # Mock dependencies
        with patch('app.drive.routes_web.file_service.get_file_by_uuid') as mock_get_file, \
             patch('app.services.zip_service.ZipService.create_zip_file', return_value='/tmp/dummy.zip') as mock_create_zip, \
             patch('app.services.zip_service.ZipService.get_recursive_items_stats', return_value={'total_size': 0, 'total_files': 0, 'skipped_encrypted': 0, 'skipped_quarantined': 0, 'skipped_missing': 0}), \
             patch('app.drive.routes_web.activity_log_service.log_activity'), \
             patch('app.drive.routes_web.current_user', user), \
             patch('flask_login.utils._get_user', return_value=user):

            file_mock = MagicMock(spec=File)
            file_mock.id = 1
            mock_get_file.return_value = file_mock

            from app.drive.routes_web import bulk_download
            try:
                bulk_download()
            except Exception:
                pass # We don't care about the response/streaming here

            # Verify that get_file_by_uuid was only called once for 'uuid1'
            mock_get_file.assert_called_once_with('uuid1', user=user, action='download')
            # Verify that create_zip_file was called with a list of one file
            args, _ = mock_create_zip.call_args
            assert len(args[1]) == 1 # files list should have 1 element
