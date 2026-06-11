"""
Description: Pytest module covering sync public security.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.extensions import db
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.public_links.services import public_link_service
from app.auth.services import auth_service
from app import create_app
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    STORAGE_PATH = "/tmp/test_storage_public_security"

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_public_link_password_protection(app):
    with app.app_context():
        u = auth_service.create_user("u", "u@e.com", "pass")
        root = folder_service.get_user_root_folder(u)
        f = File(owner_id=u.id, folder_id=root.id, original_filename="secret.txt", stored_filename="s1.bin", size_bytes=10, sha256_hash="h1", storage_path="p1")
        db.session.add(f)
        db.session.commit()

        # Create password protected link
        token, link = public_link_service.create_public_link(u, f, password="secure_pass")

        # Try to access without password
        link_rec = public_link_service.get_link_by_token(token)
        assert public_link_service.validate_password(link_rec, None) is False

        # Try with wrong password
        assert public_link_service.validate_password(link_rec, "wrong") is False

        # Try with correct password
        assert public_link_service.validate_password(link_rec, "secure_pass") is True
        assert link_rec.id == link.id

def test_sync_isolation(app):
    with app.app_context():
        u1 = auth_service.create_user("u1", "u1@e.com", "pass")
        u2 = auth_service.create_user("u2", "u2@e.com", "pass")

        # u1 creates something
        folder_service.create_folder(u1, folder_service.get_user_root_folder(u1), "U1Folder")

        from app.sync.services import sync_service
        # u2 should NOT see u1's sync events
        u2_changes = sync_service.get_changes(u2)
        assert len(u2_changes["changes"]) == 1 # Only its own root folder creation
        assert not any(c["metadata"].get("name") == "U1Folder" for c in u2_changes["changes"] if c["metadata"])

def test_antivirus_quarantine(app):
    with app.app_context():
        u = auth_service.create_user("u", "u@e.com", "pass")
        root = folder_service.get_user_root_folder(u)

        # Simulate EICAR test string upload
        from app.services.upload_service import upload_service
        import io
        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        file_obj = io.BytesIO(eicar)
        file_obj.filename = "virus.txt"

        f = upload_service.process_upload(u, root, file_obj)

        # Wait for background job (simulated synchronously in tests if executor is simple or we manually call it)
        from app.services.background_jobs import scan_virus_job
        scan_virus_job(f.id, app=app)

        db.session.refresh(f)
        assert f.is_quarantined is True

        # Verify download is blocked for quarantined file
        with pytest.raises(PermissionError, match="quarantined"):
            file_service.get_file_by_uuid(f.uuid, user=u, action='download')
