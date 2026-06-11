"""
Description: Pytest module covering name validation.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.upload_service import upload_service
from app.auth.services import auth_service
from app.models.file import File

def test_name_validation_and_duplicates(app, db, temp_storage):
    with app.app_context():
        user = auth_service.create_user("name_test", "name@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)

        # Valid name
        f1 = folder_service.create_folder(user, root, "Folder 1")
        assert f1.name == "Folder 1"

        # Duplicate folder name
        with pytest.raises(ValueError, match="already exists"):
            folder_service.create_folder(user, root, "Folder 1")

        # Empty name (after trim)
        with pytest.raises(ValueError, match="consist only of whitespace"):
            folder_service.create_folder(user, root, "   ")

        # Invalid characters
        with pytest.raises(ValueError, match="path separators"):
            folder_service.create_folder(user, root, "folder/slash")

        # File duplicates
        upload_service.process_upload(user, root, b"content", "file.txt")
        with pytest.raises(ValueError, match="already exists"):
            upload_service.process_upload(user, root, b"content", "file.txt")

        # File rename duplicate
        upload_service.process_upload(user, root, b"content", "file2.txt")
        file1_record = File.query.filter_by(original_filename="file.txt").first()

        with pytest.raises(ValueError, match="already exists"):
            file_service.rename_file(user, file1_record, "file2.txt")
