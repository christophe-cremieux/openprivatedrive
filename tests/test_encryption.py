"""
Description: Pytest module covering encryption.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from io import BytesIO
from app.models.file import File
from app.services.upload_service import upload_service
from app.services.file_service import file_service
from app.public_links.services import public_link_service
from app.extensions import db

def test_encrypted_upload_and_decryption(app, client, test_user_factory, temp_storage):
    """Test end-to-end encrypted upload and decryption."""
    user = test_user_factory(password="password")
    client.post("/login", data={"username": "testuser", "password": "password"})

    # 1. Upload encrypted file
    content = b"This is a very secret message."
    data = {
        'file': (BytesIO(content), 'secret.txt'),
        'is_encrypted': 'true',
        'password': 'strongpassword123'
    }
    response = client.post('/upload', data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"secret.txt" in response.data

    with app.app_context():
        file_rec = File.query.filter_by(original_filename='secret.txt').first()
        assert file_rec.is_encrypted is True
        assert file_rec.encryption_metadata['algorithm'] == 'AES-256-GCM'
        assert file_rec.encryption_metadata['encrypted_original_size'] == len(content)

        # Verify stored hash is of encrypted bytes, not plaintext
        # (Very unlikely hash matches plaintext content)
        import hashlib
        assert file_rec.sha256_hash != hashlib.sha256(content).hexdigest()

    # 2. Attempt download without password (should redirect to decrypt)
    response = client.get(f'/files/{file_rec.uuid}/download', follow_redirects=False)
    assert response.status_code == 302
    assert '/decrypt' in response.headers['Location']

    # 3. Decrypt with wrong password
    response = client.post(f'/files/{file_rec.uuid}/decrypt', data={'password': 'wrong'}, follow_redirects=True)
    assert b"Decryption failed" in response.data

    # 4. Decrypt with correct password
    response = client.post(f'/files/{file_rec.uuid}/decrypt', data={'password': 'strongpassword123'})
    assert response.status_code == 200
    assert response.data == content
    assert 'secret.txt' in response.headers['Content-Disposition']

def test_encrypted_file_restrictions(app, client, test_user_factory, temp_storage):
    """Test that encrypted files have no previews or public links."""
    user = test_user_factory()

    with app.app_context():
        from app.services.folder_service import folder_service
        root = folder_service.get_user_root_folder(user)

        file_rec = upload_service.process_upload(
            user, root, b"secrets", filename="hidden.txt",
            is_encrypted=True, password="password123456"
        )
        db.session.commit()

        # Check Preview Service
        from app.services.preview_service import preview_service
        assert preview_service.get_preview_type(file_rec) == 'encrypted'
        assert preview_service.is_previewable(file_rec) is False

        # Check Public Link Restriction
        with pytest.raises(ValueError) as excinfo:
            public_link_service.create_public_link(user, file_rec)
        assert "encrypted" in str(excinfo.value)

def test_search_excludes_encrypted_content(app, client, test_user_factory, temp_storage):
    """Test that content search does not return encrypted files."""
    user = test_user_factory()

    with app.app_context():
        from app.services.folder_service import folder_service
        root = folder_service.get_user_root_folder(user)

        # 1. Normal file with text
        f1 = upload_service.process_upload(user, root, b"findme in plaintext", filename="plain.txt")
        # Manually set extracted text because background jobs don't run in tests easily
        f1.preview_metadata = {'extracted_text': "findme in plaintext"}

        # 2. Encrypted file that would have "findme" if decrypted
        upload_service.process_upload(
            user, root, b"findme in secret", filename="secret.txt",
            is_encrypted=True, password="password123456"
        )
        db.session.commit()

        # Search for "findme"
        results = file_service.search_files(user, query="findme")
        filenames = [f.original_filename for f in results]

        assert "plain.txt" in filenames
        assert "secret.txt" not in filenames

def test_api_decryption(app, client, test_user_factory, temp_storage):
    """Test API decryption endpoint."""
    user = test_user_factory(password="api-pass")

    with app.app_context():
        from app.services.folder_service import folder_service
        root = folder_service.get_user_root_folder(user)

        content = b"api secret"
        file_rec = upload_service.process_upload(
            user, root, content, filename="api.txt",
            is_encrypted=True, password="api-password-123"
        )
        db.session.commit()
        file_uuid = file_rec.uuid

    # Get API Token
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "api-pass",
        "device_id": "test",
        "device_name": "test"
    })
    token = login_resp.get_json()['data']['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    resp = client.get(f'/api/v1/files/{file_uuid}', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['is_encrypted'] is True
    assert data['requires_password_for_download'] is True

    # Decrypt Download
    resp = client.post(f'/api/v1/files/{file_uuid}/decrypt-download',
                       json={'password': 'api-password-123'},
                       headers=headers)
    assert resp.status_code == 200
    assert resp.data == content

    # Wrong password
    resp = client.post(f'/api/v1/files/{file_uuid}/decrypt-download',
                       json={'password': 'wrong'},
                       headers=headers)
    assert resp.status_code == 401

def test_decrypt_temp_file_cleanup(app, client, test_user_factory, temp_storage):
    """Test that temporary decrypted files are removed after download."""
    import os
    user = test_user_factory(password="password")
    client.post("/login", data={"username": "testuser", "password": "password"})

    content = b"cleanup test content"
    with app.app_context():
        from app.services.folder_service import folder_service
        root = folder_service.get_user_root_folder(user)
        file_rec = upload_service.process_upload(
            user, root, content, filename="cleanup.txt",
            is_encrypted=True, password="password123456"
        )
        db.session.commit()
        file_uuid = file_rec.uuid

    # We need to capture the temp path created during decryption.
    # Since it's inside the route, we can't easily get it unless we mock or spy.
    # However, we can check for any leftover files in the system's temp dir.
    import tempfile
    temp_dir = tempfile.gettempdir()

    # We should take the snapshot AFTER upload to avoid catching upload artifacts
    initial_files = set(os.listdir(temp_dir))

    response = client.post(f'/files/{file_uuid}/decrypt', data={'password': 'password123456'})
    assert response.status_code == 200
    assert response.data == content
    response.close() # Explicitly close to trigger call_on_close

    # Response is now closed in the test client after response.data is accessed or at end of scope.
    # Let's check for new files in temp_dir that might have leaked.
    final_files = set(os.listdir(temp_dir))
    new_files = final_files - initial_files

    # Filtering for files that look like they came from NamedTemporaryFile
    # (usually starts with 'tmp' followed by random chars)
    leaked_tmp_files = [f for f in new_files if f.startswith('tmp')]

    # In some environments, the upload_service or other parts might leave temp files
    # during the setup phase of the test itself.
    # Let's try to find if any of these files are NOT from the decryption itself.
    # Actually, the most reliable way is to check the count.

    # During upload, process_upload creates a temp file and deletes it.
    # NamedTemporaryFile(delete=False) is used there too.
    # Os.remove(tmp_path) is called in 'finally'.

    assert len(leaked_tmp_files) == 0

def test_copy_encrypted_file(app, client, test_user_factory, temp_storage):
    """Test that copying an encrypted file preserves its encryption."""
    user = test_user_factory()

    with app.app_context():
        from app.services.folder_service import folder_service
        root = folder_service.get_user_root_folder(user)

        original = upload_service.process_upload(
            user, root, b"secret content", filename="original.txt",
            is_encrypted=True, password="password123456"
        )
        db.session.commit()

        # Copy the file
        copy = file_service.copy_file(user, original, root)
        db.session.commit()

        assert copy.is_encrypted is True
        assert copy.encryption_version == original.encryption_version
        assert copy.encryption_salt == original.encryption_salt
        assert copy.encryption_nonce == original.encryption_nonce
        assert copy.encryption_metadata == original.encryption_metadata
        assert copy.sha256_hash == original.sha256_hash
        assert copy.original_filename.startswith("original")
        assert copy.uuid != original.uuid

        # Verify the copy can be decrypted with the same password
        from app.services.encryption_service import encryption_service
        from app.services.storage_service import storage_service
        import io

        full_path = storage_service.get_full_path(copy.storage_path)
        with open(full_path, 'rb') as f_in:
            out = io.BytesIO()
            encryption_service.decrypt_stream(
                f_in, out, "password123456",
                copy.encryption_salt,
                copy.encryption_nonce,
                copy.encryption_metadata
            )
            assert out.getvalue() == b"secret content"
