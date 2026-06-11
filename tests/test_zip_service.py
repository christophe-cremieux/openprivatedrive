"""
Description: Pytest module covering zip service.
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
from unittest.mock import patch
from app.models.file import File
from app.models.folder import Folder
from app.services.zip_service import zip_service
from app.extensions import db

def test_get_recursive_items_stats_skipped_behavior(app, db, test_user_factory):
    """Test that ZipService correctly counts and skips items based on state/permissions."""
    user = test_user_factory()
    # Need to mock can_access because it relies on complex permission logic
    with app.app_context(), \
         patch('app.services.zip_service.can_access', return_value=True):
        # 1. Setup structure
        root = Folder(name="Root", owner_id=user.id)
        db.session.add(root)
        db.session.commit()

        # Regular file
        f1 = File(original_filename="f1.txt", folder_id=root.id, owner_id=user.id, size_bytes=100,
                  storage_path="fake/f1.bin", stored_filename="f1.bin", sha256_hash="hash1")
        # Encrypted file
        f2 = File(original_filename="f2.txt", folder_id=root.id, owner_id=user.id, size_bytes=200,
                  storage_path="fake/f2.bin", is_encrypted=True, stored_filename="f2.bin", sha256_hash="hash2")
        # Quarantined file
        f3 = File(original_filename="f3.txt", folder_id=root.id, owner_id=user.id, size_bytes=300,
                  storage_path="fake/f3.bin", scan_status="infected", is_quarantined=True, stored_filename="f3.bin", sha256_hash="hash3")
        # Missing file (will mock os.path.exists)
        f4 = File(original_filename="f4.txt", folder_id=root.id, owner_id=user.id, size_bytes=400,
                  storage_path="fake/f4.bin", stored_filename="f4.bin", sha256_hash="hash4")

        db.session.add_all([f1, f2, f3, f4])
        db.session.commit()

        # Mock storage_service and os.path.exists
        with patch('app.services.zip_service.storage_service.get_full_path', side_effect=lambda x: f"/tmp/{x}"), \
             patch('app.services.zip_service.os.path.exists', side_effect=lambda x: x == "/tmp/fake/f1.bin"):

            stats = zip_service.get_recursive_items_stats(user, [f1, f2, f3, f4], [])

            assert stats['total_files'] == 1
            assert stats['total_size'] == 100
            assert stats['skipped_encrypted'] == 1
            assert stats['skipped_quarantined'] == 1
            assert stats['skipped_missing'] == 1

def test_get_recursive_items_stats_nested_behavior(app, db, test_user_factory):
    """Test recursive behavior of stats calculation."""
    user = test_user_factory()
    with app.app_context(), \
         patch('app.services.zip_service.can_access', return_value=True):
        root = Folder(name="Root", owner_id=user.id)
        db.session.add(root)
        db.session.commit()

        sub = Folder(name="Sub", owner_id=user.id, parent_id=root.id)
        db.session.add(sub)
        db.session.commit()

        # File in root
        f1 = File(original_filename="f1.txt", folder_id=root.id, owner_id=user.id, size_bytes=100,
                  storage_path="fake/f1.bin", stored_filename="f1.bin", sha256_hash="hash1")
        # File in sub
        f2 = File(original_filename="f2.txt", folder_id=sub.id, owner_id=user.id, size_bytes=200,
                  storage_path="fake/f2.bin", stored_filename="f2.bin", sha256_hash="hash2")
        # Encrypted in sub
        f3 = File(original_filename="f3.txt", folder_id=sub.id, owner_id=user.id, size_bytes=300,
                  storage_path="fake/f3.bin", is_encrypted=True, stored_filename="f3.bin", sha256_hash="hash3")

        db.session.add_all([f1, f2, f3])
        db.session.commit()

        with patch('app.services.zip_service.os.path.exists', return_value=True):
            db.session.expire_all()
            root = db.session.get(Folder, root.id)
            stats = zip_service.get_recursive_items_stats(user, [], [root])

            assert stats['total_files'] == 2
            assert stats['total_size'] == 300
            assert stats['skipped_encrypted'] == 1
