"""
Description: Pytest module covering edge cases.
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
from datetime import datetime, timedelta, timezone
from app.extensions import db
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.models.public_link import PublicLink
from app.services.folder_service import folder_service
from app.public_links.services import public_link_service
from app.sharing.services import sharing_service

def test_expired_public_link_access(app, db, test_user_factory, client):
    """Test that expired public links are not accessible."""
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # Create an expired link
        expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        # We need to use naive datetime for the DB as per conventions
        expires_at_naive = expires_at.replace(tzinfo=None)

        raw_token, link = public_link_service.create_public_link(
            user, root, expires_at=expires_at_naive
        )
        link_uuid = link.uuid

    # Attempt to access the link
    response = client.get(f'/public/l/{raw_token}')
    assert response.status_code == 404

def test_permission_inheritance_and_override(app, db, test_user_factory):
    """Test that nested folder permissions inherit and can be overridden."""
    owner = test_user_factory()
    with app.app_context():
        other = User(username='other', email='other@example.com')
        other.set_password('password123')
        db.session.add(other)
        db.session.commit()

        root = folder_service.get_user_root_folder(owner)
        parent = folder_service.create_folder(owner, root, "Parent")
        child = folder_service.create_folder(owner, parent, "Child")

        # Share parent with 'viewer'
        sharing_service.share_resource(owner, parent, 'other', 'viewer')

        # Check inheritance
        from app.drive.permissions import get_effective_permission
        assert get_effective_permission(other, child) == 'viewer'

        # Explicit override on child with 'editor'
        sharing_service.share_resource(owner, child, 'other', 'editor')
        assert get_effective_permission(other, child) == 'editor'

        # Verify parent is still 'viewer'
        assert get_effective_permission(other, parent) == 'viewer'

def test_public_link_max_downloads_enforcement(app, db, test_user_factory, client, temp_storage):
    """Test that public links respect max_downloads."""
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # Create a dummy file
        from app.services.storage_service import storage_service
        storage_path = "test_max_dl.txt"
        full_path = storage_service.get_full_path(storage_path)
        with open(full_path, "w") as f:
            f.write("test content")

        file_record = File(
            owner_id=user.id,
            folder_id=root.id,
            original_filename="test.txt",
            stored_filename="test_max_dl.txt",
            storage_path=storage_path,
            size_bytes=12,
            mime_type="text/plain",
            sha256_hash="hash"
        )
        db.session.add(file_record)
        db.session.commit()

        raw_token, link = public_link_service.create_public_link(
            user, file_record, max_downloads=1
        )

    # First access - OK (GET)
    response = client.get(f'/public/l/{raw_token}')
    assert response.status_code == 200

    # POST to "download"
    response = client.post(f'/public/l/{raw_token}')
    assert response.status_code == 200

    # Second access - Should be 404
    response = client.get(f'/public/l/{raw_token}')
    assert response.status_code == 404

def test_folder_auto_encryption_policy_inheritance(app, db, test_user_factory):
    """Test that folders inherit or don't inherit auto-encryption policy."""
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        parent = folder_service.create_folder(user, root, "SecretParent")
        parent.encrypt_new_uploads = True
        db.session.commit()

        # New child should NOT automatically have the policy enabled (it's per folder)
        child = folder_service.create_folder(user, parent, "Child")
        assert child.encrypt_new_uploads is False

def test_blocked_extensions(app, db, test_user_factory, temp_storage):
    """Test that blocked extensions are rejected during upload."""
    user = test_user_factory()
    from app.services.upload_service import upload_service

    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # Test .ps1 (script)
        with pytest.raises(ValueError) as exc:
            upload_service.process_upload(user, root, b"echo hello", filename="test.ps1")
        assert "blocked for security reasons" in str(exc.value)

        # Test .exe (executable)
        with pytest.raises(ValueError) as exc:
            upload_service.process_upload(user, root, b"MZ...", filename="test.exe")
        assert "blocked for security reasons" in str(exc.value)

def test_trash_lifecycle(app, db, test_user_factory, temp_storage):
    """Test soft-delete, restore, and permanent delete lifecycle."""
    user = test_user_factory()
    from app.services.file_service import file_service
    from app.services.storage_service import storage_service

    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # 1. Create a file
        full_path = storage_service.get_full_path("trash_test.txt")
        with open(full_path, "w") as f: f.write("content")

        file_record = File(
            owner_id=user.id, folder_id=root.id,
            original_filename="trash_test.txt", stored_filename="trash_test.bin",
            storage_path="trash_test.txt", size_bytes=7,
            mime_type="text/plain", sha256_hash="hash"
        )
        db.session.add(file_record)
        db.session.commit()
        file_uuid = file_record.uuid

        # 2. Soft delete
        file_service.delete_file(user, file_uuid)
        db.session.refresh(file_record)
        assert file_record.is_deleted is True
        assert file_record.deleted_at is not None

        # 3. Restore
        file_service.restore_file(user, file_record)
        db.session.refresh(file_record)
        assert file_record.is_deleted is False
        assert file_record.deleted_at is None

        # 4. Permanent delete (must be in trash first)
        file_service.delete_file(user, file_uuid)
        file_service.delete_file(user, file_uuid, permanent=True)
        assert File.query.filter_by(uuid=file_uuid).first() is None
        assert not os.path.exists(full_path)

def test_signature_mismatch(app, db, test_user_factory, temp_storage):
    """Test that renaming a dangerous file to a safe extension is caught by signature validation."""
    user = test_user_factory()
    from app.services.upload_service import upload_service

    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # PNG signature but actually a script (simulated)
        # Note: validate_file_signature checks if header matches signature.
        # If we provide a .jpg extension but the file starts with %PDF-, it should fail.

        pdf_content = b"%PDF-1.4\n..."
        with pytest.raises(ValueError) as exc:
            upload_service.process_upload(user, root, pdf_content, filename="not_a_pdf.jpg")
        assert "File signature mismatch" in str(exc.value)
