"""
Description: Pytest module covering previews.
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
from app.services.preview_service import preview_service
from io import BytesIO
import io
import os

def test_preview_service_get_preview_type(app):
    with app.app_context():
        # Image
        f_img = File(mime_type='image/png', original_filename='test.png')
        assert preview_service.get_preview_type(f_img) == 'image'

        # PDF
        f_pdf = File(mime_type='application/pdf', original_filename='test.pdf')
        assert preview_service.get_preview_type(f_pdf) == 'pdf'

        # Text
        f_txt = File(mime_type='text/plain', original_filename='test.txt')
        assert preview_service.get_preview_type(f_txt) == 'text'

        # Text-like source/data files
        f_json = File(mime_type='application/json', original_filename='settings.json')
        assert preview_service.get_preview_type(f_json) == 'text'

        f_md = File(mime_type='text/markdown', original_filename='README.md')
        assert preview_service.get_preview_type(f_md) == 'text'

        f_js = File(mime_type='application/javascript', original_filename='app.js')
        assert preview_service.get_preview_type(f_js) == 'text'

        # CSV
        f_csv = File(mime_type='text/csv', original_filename='test.csv')
        assert preview_service.get_preview_type(f_csv) == 'csv'

        # Unsupported
        f_zip = File(mime_type='application/zip', original_filename='test.zip')
        assert preview_service.get_preview_type(f_zip) == 'unsupported'

        # Quarantined
        f_inf = File(mime_type='image/png', is_quarantined=True)
        assert preview_service.get_preview_type(f_inf) == 'blocked'

def test_preview_routes(client, test_user_factory, db, temp_storage):
    user = test_user_factory()
    # Authenticate
    client.post("/login", data={"username": user.username, "password": "password"})

    # Create a text file
    content = b"Hello, world!"
    f_uuid = "test-uuid-123"
    shard1, shard2 = f_uuid[0:2], f_uuid[2:4]
    rel_path = os.path.join("files", shard1, shard2, f"{f_uuid}.bin")
    abs_path = os.path.join(temp_storage, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'wb') as f:
        f.write(content)

    file_rec = File(
        uuid=f_uuid,
        owner_id=user.id,
        original_filename='test.txt',
        stored_filename=f"{f_uuid}.bin",
        mime_type='text/plain',
        size_bytes=len(content),
        sha256_hash='hash',
        storage_path=rel_path
    )
    db_session = db.session
    db_session.add(file_rec)
    db_session.commit()

    # Test Web Preview
    resp = client.get(f'/files/{f_uuid}/preview')
    assert resp.status_code == 200
    assert b"Hello, world!" in resp.data

    # Test Raw Preview
    resp = client.get(f'/files/{f_uuid}/raw-preview')
    assert resp.status_code == 200
    assert resp.data == content
    assert resp.mimetype == 'text/plain'

def test_text_like_extension_preview_reads_content(app, db, temp_storage):
    content = b'{"enabled": true, "name": "demo"}'
    f_uuid = "json-preview-uuid"
    shard1, shard2 = f_uuid[0:2], f_uuid[2:4]
    rel_path = os.path.join("files", shard1, shard2, f"{f_uuid}.bin")
    abs_path = os.path.join(temp_storage, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'wb') as f:
        f.write(content)

    file_rec = File(
        uuid=f_uuid,
        owner_id=1,
        original_filename='settings.json',
        stored_filename=f"{f_uuid}.bin",
        mime_type='application/octet-stream',
        size_bytes=len(content),
        sha256_hash='hash',
        storage_path=rel_path
    )

    with app.app_context():
        assert preview_service.get_preview_type(file_rec) == 'text'
        assert '"enabled": true' in preview_service.get_safe_text_preview(file_rec)

def test_thumbnail_route_permissions(client, test_user_factory, db):
    owner = test_user_factory(username="owner", email="owner@example.com")
    other = test_user_factory(username="other", email="other@example.com")

    file_rec = File(
        uuid='thumb-uuid',
        owner_id=owner.id,
        original_filename='test.png',
        stored_filename='test.png',
        mime_type='image/png',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path'
    )
    db.session.add(file_rec)
    db.session.commit()

    # Owner can access (but gets 404 because physical file doesn't exist)
    client.post("/login", data={"username": "owner", "password": "password"})
    resp = client.get('/files/thumb-uuid/thumbnail/small')
    assert resp.status_code == 404
    client.get("/logout")

    # Other user cannot access
    client.post("/login", data={"username": "other", "password": "password"})
    resp = client.get('/files/thumb-uuid/thumbnail/small')
    assert resp.status_code == 403

def test_api_preview_fields(client, test_user_factory, db):
    user = test_user_factory()
    from app.services.folder_service import folder_service
    root = folder_service.get_user_root_folder(user)

    file_rec = File(
        uuid='api-preview-uuid',
        owner_id=user.id,
        folder_id=root.id,
        original_filename='test.png',
        stored_filename='test.png',
        mime_type='image/png',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path',
        preview_metadata={'thumbnail_status': 'ready', 'thumbnails': {'small': 's', 'large': 'l'}}
    )
    db.session.add(file_rec)
    db.session.commit()

    # Get API token
    resp = client.post('/api/v1/auth/login', json={"username": user.username, "password": "password"})
    token = resp.get_json()['data']['access_token']

    resp = client.get(f'/api/v1/folders/{root.uuid}', headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    item = next(i for i in data['items'] if i['uuid'] == 'api-preview-uuid')

    assert item['previewable'] is True
    assert item['preview_type'] == 'image'
    assert 'preview_url' in item
    assert item['thumbnail_status'] == 'ready'
    assert 'thumbnail_small_url' in item
    assert 'thumbnail_large_url' in item

def test_office_preview_logic(app, db):
    with app.app_context():
        # Pending
        f_pending = File(
            mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            preview_metadata={'office_preview_status': 'pending'}
        )
        assert preview_service.get_preview_type(f_pending) == 'office_pending'
        # Pending is NOT previewable for the API, but handles by Web UI separately
        assert preview_service.is_previewable(f_pending) is False

        # Ready
        f_ready = File(
            mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            preview_metadata={'office_preview_status': 'ready'}
        )
        assert preview_service.get_preview_type(f_ready) == 'office_pdf'

        # Failed
        f_failed = File(
            mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            preview_metadata={'office_preview_status': 'failed'}
        )
        assert preview_service.get_preview_type(f_failed) == 'office_failed'

def test_office_preview_route_permissions(client, test_user_factory, db):
    owner = test_user_factory(username="owner2", email="owner2@example.com")
    other = test_user_factory(username="other2", email="other2@example.com")

    file_rec = File(
        uuid='office-uuid',
        owner_id=owner.id,
        original_filename='test.docx',
        stored_filename='test.docx',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path',
        preview_metadata={'office_preview_status': 'ready', 'office_preview_path': 'previews/test.pdf'}
    )
    db.session.add(file_rec)
    db.session.commit()

    # Owner can access (gets 404 if physical file missing)
    client.post("/login", data={"username": "owner2", "password": "password"})
    resp = client.get('/files/office-uuid/office-preview.pdf')
    assert resp.status_code == 404
    client.get("/logout")

    # Other user cannot access
    client.post("/login", data={"username": "other2", "password": "password"})
    resp = client.get('/files/office-uuid/office-preview.pdf')
    assert resp.status_code == 403

def test_quarantined_office_preview_blocked(client, test_user_factory, db):
    user = test_user_factory(username="q-user", email="q@example.com")
    file_rec = File(
        uuid='office-q-uuid',
        owner_id=user.id,
        original_filename='test.docx',
        stored_filename='test.docx.bin',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='files/of/fi/office-q-uuid.bin',
        is_quarantined=True,
        preview_metadata={'office_preview_status': 'ready', 'office_preview_path': 'previews/test.pdf'}
    )
    db.session.add(file_rec)
    db.session.commit()

    client.get("/logout") # Ensure we are logged out from previous tests
    login_resp = client.post("/login", data={"username": "q-user", "password": "password"})
    assert login_resp.status_code == 302

    # Web Route
    # Note: get_office_preview uses login_required, and get_file_by_uuid (if user is passed)
    # also checks for quarantine.
    resp = client.get('/files/office-q-uuid/office-preview.pdf', follow_redirects=False)
    assert resp.status_code == 403

    # API Route
    resp = client.post('/api/v1/auth/login', json={"username": "q-user", "password": "password"})
    token = resp.get_json()['data']['access_token']
    resp = client.get('/api/v1/files/office-q-uuid/office-preview', headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

def test_copied_file_metadata_reset(client, test_user_factory, db):
    user = test_user_factory(username="copyuser", email="copy@example.com")
    from app.services.folder_service import folder_service
    root = folder_service.get_user_root_folder(user)

    file_rec = File(
        uuid='original-uuid',
        owner_id=user.id,
        folder_id=root.id,
        original_filename='original.docx',
        stored_filename='original.bin',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='files/or/ig/original.bin',
        preview_metadata={
            'office_preview_status': 'ready',
            'office_preview_path': 'previews/original.pdf',
            'thumbnails': {'small': 'thumb.webp'}
        }
    )
    db.session.add(file_rec)
    db.session.commit()

    from app.services.file_service import file_service
    # Mocking backend.copy to avoid physical file operations
    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.services.storage_service.LocalStorageBackend.copy", lambda self, s, d: f"files/co/py/{d}.bin")

        copy_rec = file_service.copy_file(user, file_rec, root)

        assert copy_rec.uuid != file_rec.uuid
        assert copy_rec.preview_metadata.get('office_preview_status') is None
        assert 'office_preview_path' not in copy_rec.preview_metadata
        assert 'thumbnails' not in copy_rec.preview_metadata
        assert copy_rec.preview_metadata.get('thumbnail_status') == 'none'

def test_permanent_delete_cleanup(app, db, test_user_factory, monkeypatch):
    user = test_user_factory(username="deluser", email="del@example.com")

    file_rec = File(
        uuid='del-uuid',
        owner_id=user.id,
        original_filename='del.docx',
        stored_filename='del.bin',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='files/de/l/del.bin',
        preview_metadata={
            'office_preview_status': 'ready',
            'office_preview_path': 'previews/del.pdf',
            'thumbnails': {'small': 'thumb-del.webp'}
        }
    )
    db.session.add(file_rec)
    db.session.commit()

    deleted_paths = []
    def mock_delete(rel_path):
        deleted_paths.append(rel_path)

    monkeypatch.setattr("app.services.storage_service.storage_service.delete_file", mock_delete)

    from app.services.file_service import file_service
    with app.app_context():
        # Get the record from the current session
        file_rec = db.session.get(File, file_rec.id)
        file_service.permanent_delete_file(user, file_rec)

        assert 'files/de/l/del.bin' in deleted_paths
        assert 'previews/del.pdf' in deleted_paths
        assert 'thumb-del.webp' in deleted_paths

def test_api_pending_office_file(client, test_user_factory, db):
    user = test_user_factory(username="apiuser2", email="api2@example.com")
    from app.services.folder_service import folder_service
    root = folder_service.get_user_root_folder(user)

    file_rec = File(
        uuid='api-pending-uuid',
        owner_id=user.id,
        folder_id=root.id,
        original_filename='pending.docx',
        stored_filename='pending.bin',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path',
        preview_metadata={'office_preview_status': 'pending'}
    )
    db.session.add(file_rec)
    db.session.commit()

    # Get API token
    resp = client.post('/api/v1/auth/login', json={"username": "apiuser2", "password": "password"})
    token = resp.get_json()['data']['access_token']

    resp = client.get(f'/api/v1/folders/{root.uuid}', headers={"Authorization": f"Bearer {token}"})
    item = next(i for i in resp.get_json()['data']['items'] if i['uuid'] == 'api-pending-uuid')

    assert item['previewable'] is False
    assert item['preview_status'] == 'pending'
    assert 'preview_url' not in item

def test_media_upload_validation(client, test_user_factory, db, temp_storage):
    user = test_user_factory(username="mediauser", email="media@example.com")
    client.post("/login", data={"username": "mediauser", "password": "password"})

    # Valid MP3
    valid_mp3 = b'ID3' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (BytesIO(valid_mp3), 'test.mp3')}, content_type='multipart/form-data')
    assert resp.status_code == 302

    # Valid MP4 (ftyp)
    valid_mp4 = b'\x00\x00\x00\x18ftyp' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (BytesIO(valid_mp4), 'test.mp4')}, content_type='multipart/form-data')
    assert resp.status_code == 302

    # Invalid MP3 (signature mismatch)
    invalid_mp3 = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (BytesIO(invalid_mp3), 'test_bad.mp3')}, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200 # Flashed error and re-rendered dashboard
    assert b"File signature mismatch" in resp.data

    # Check if files were actually added
    from app.models.file import File
    with client.application.app_context():
        f_mp3 = File.query.filter_by(original_filename='test.mp3').first()
        assert f_mp3 is not None
        assert f_mp3.mime_type == 'audio/mpeg'
        assert preview_service.get_preview_type(f_mp3) == 'audio'

        f_mp4 = File.query.filter_by(original_filename='test.mp4').first()
        assert f_mp4 is not None
        assert f_mp4.mime_type == 'video/mp4'
        assert preview_service.get_preview_type(f_mp4) == 'video'

def test_media_preview_fields_api(client, test_user_factory, db):
    user = test_user_factory(username="apiuser3", email="api3@example.com")
    from app.services.folder_service import folder_service
    root = folder_service.get_user_root_folder(user)

    file_rec = File(
        uuid='api-audio-uuid',
        owner_id=user.id,
        folder_id=root.id,
        original_filename='test.mp3',
        stored_filename='test.bin',
        mime_type='audio/mpeg',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path'
    )
    db.session.add(file_rec)
    db.session.commit()

    # Get API token
    resp = client.post('/api/v1/auth/login', json={"username": "apiuser3", "password": "password"})
    token = resp.get_json()['data']['access_token']

    resp = client.get(f'/api/v1/folders/{root.uuid}', headers={"Authorization": f"Bearer {token}"})
    item = next(i for i in resp.get_json()['data']['items'] if i['uuid'] == 'api-audio-uuid')

    assert item['previewable'] is True
    assert item['preview_type'] == 'audio'
    assert item['preview_status'] == 'ready'
    assert 'preview_url' in item
