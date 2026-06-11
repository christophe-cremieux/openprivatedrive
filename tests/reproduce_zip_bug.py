"""
Description: Pytest module covering reproduce zip bug.
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

def test_reproduce_zip_duplication_and_structure(app, db, test_user_factory):
    """Reproduce the issue where duplicate UUIDs cause double items and 'Selected items' folder exists."""
    user = test_user_factory()
    with app.app_context():
        # Setup: A folder and a file
        folder = Folder(name="black", owner_id=user.id)
        db.session.add(folder)
        db.session.commit()

        # Add a file to the folder so it's not empty and shows up in ZIP
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

            # Simulate duplicates as received from UI
            files = [file, file]
            folders = [folder, folder]

            zip_path = zip_service.create_zip_file(user, files, folders)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    namelist = zf.namelist()
                    print(f"ZIP namelist: {namelist}")

                    # 1. Check for "Selected items" prefix (Bug)
                    assert any(name.startswith("Selected items/") for name in namelist), "Expected 'Selected items/' prefix to be present (reproducing the bug)"

                    # 2. Check for duplicates (Bug)
                    assert "black/inner.txt" in namelist
                    assert "black_1/inner.txt" in namelist

                    assert "Selected items/headphone.png" in namelist
                    assert "Selected items/headphone_1.png" in namelist
            finally:
                if os.path.exists(zip_path):
                    os.remove(zip_path)

if __name__ == "__main__":
    # This is just for documentation, pytest will run it
    pass
