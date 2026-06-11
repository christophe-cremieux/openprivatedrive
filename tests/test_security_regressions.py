"""
Description: Pytest module covering security regressions.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.upload_service import upload_service
from app.public_links.services import public_link_service
from app.auth.services import auth_service
from datetime import datetime, timedelta, timezone
from io import BytesIO

def test_idor_folder_access(app, db, test_user_factory, client):
    user_a = test_user_factory("user_a", "a@ex.com")
    user_b = test_user_factory("user_b", "b@ex.com")

    with app.app_context():
        root_b = folder_service.get_user_root_folder(user_b)
        folder_b = folder_service.create_folder(user_b, root_b, "B Folder")

        # Authenticate as user_a
        client.post("/login", data={"username": "user_a", "password": "password"})

        # Try to access user_b's folder
        response = client.get(f"/folders/{folder_b.uuid}")
        assert response.status_code == 403

def test_idor_file_download(app, db, test_user_factory, client, temp_storage):
    user_a = test_user_factory("user_a", "a@ex.com")
    user_b = test_user_factory("user_b", "b@ex.com")

    with app.app_context():
        root_b = folder_service.get_user_root_folder(user_b)
        file_b = upload_service.process_upload(user_b, root_b, b"private", "b.txt")

        # Authenticate as user_a
        client.post("/login", data={"username": "user_a", "password": "password"})

        # Try to download user_b's file
        response = client.get(f"/files/{file_b.uuid}/download")
        assert response.status_code == 403

def test_deleted_file_access(app, db, test_user_factory, client, temp_storage):
    user = test_user_factory()

    with app.app_context():
        root = folder_service.get_user_root_folder(user)
        file = upload_service.process_upload(user, root, b"to be deleted", "delete.txt")

        # Soft delete
        file_service.soft_delete_file(user, file)

        client.post("/login", data={"username": "testuser", "password": "password"})

        # Try to download deleted file
        response = client.get(f"/files/{file.uuid}/download")
        # get_file_by_uuid filters out deleted files, so it returns 404
        assert response.status_code in [403, 404]

def test_upload_extension_validation(app, db, test_user_factory, client, temp_storage, monkeypatch):
    # Mock allowed extensions if necessary, but assuming there's some default blacklist/whitelist
    user = test_user_factory()
    client.post("/login", data={"username": "testuser", "password": "password"})

    with app.app_context():
        root = folder_service.get_user_root_folder(user)

        # Assuming .exe is blocked or not in whitelist
        data = {
            'file': (BytesIO(b"malicious"), 'virus.exe'),
            'folder_uuid': root.uuid
        }
        response = client.post("/upload", data=data, content_type='multipart/form-data')
        # Check if error message or redirect with flash
        assert response.status_code in [200, 302]
        # In this app, it seems it flashes an error and redirects
        if response.status_code == 302:
            response = client.get(response.location, follow_redirects=True)
        assert b"blocked for security reasons" in response.data or b"is not allowed" in response.data

def test_public_link_security_hashing(app, db, test_user_factory):
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)
        file = upload_service.process_upload(user, root, b"data", "file.txt")

        raw_token, link = public_link_service.create_public_link(user, file)

        # Ensure raw token is not in DB
        assert raw_token not in link.token_hash
        assert len(link.token_hash) == 64 # SHA256

def test_expired_public_link_access(app, db, test_user_factory, client, temp_storage):
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)
        file = upload_service.process_upload(user, root, b"data", "file.txt")

        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        raw_token, link = public_link_service.create_public_link(user, file, expires_at=past_date)

        response = client.get(f"/public/l/{raw_token}")
        assert response.status_code == 404

def test_one_time_public_link(app, db, test_user_factory, client, temp_storage):
    user = test_user_factory()
    with app.app_context():
        root = folder_service.get_user_root_folder(user)
        file = upload_service.process_upload(user, root, b"data", "file.txt")

        # Max downloads = 1
        raw_token, link = public_link_service.create_public_link(user, file, max_downloads=1)

        # First access (POST because it might be password protected, but here it's not)
        # Actually view_link handles GET and POST.
        response = client.post(f"/public/l/{raw_token}", data={}, follow_redirects=True)
        assert response.status_code == 200

        # Second access
        response = client.get(f"/public/l/{raw_token}")
        assert response.status_code == 404
