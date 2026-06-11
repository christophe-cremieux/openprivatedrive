"""
Description: Pytest module covering media.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
import io
from app.models.file import File
from app.services.preview_service import preview_service

def test_media_upload_validation(client, test_user_factory, db, temp_storage):
    user = test_user_factory(username="mediauser", email="media@example.com")
    client.post("/login", data={"username": "mediauser", "password": "password"})

    # Valid MP3
    valid_mp3 = b'ID3' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (io.BytesIO(valid_mp3), 'test.mp3')}, content_type='multipart/form-data')
    assert resp.status_code == 302

    # Valid MP4 (ftyp)
    valid_mp4 = b'\x00\x00\x00\x18ftyp' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (io.BytesIO(valid_mp4), 'test.mp4')}, content_type='multipart/form-data')
    assert resp.status_code == 302

    # Invalid MP3 (signature mismatch - using PNG header for MP3)
    invalid_mp3 = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
    resp = client.post('/upload', data={'file': (io.BytesIO(invalid_mp3), 'test_bad.mp3')}, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b"File signature mismatch" in resp.data

    # Check if valid files were actually added
    with client.application.app_context():
        f_mp3 = File.query.filter_by(original_filename='test.mp3').first()
        assert f_mp3 is not None
        assert f_mp3.mime_type == 'audio/mpeg'
        assert preview_service.get_preview_type(f_mp3) == 'audio'

        f_mp4 = File.query.filter_by(original_filename='test.mp4').first()
        assert f_mp4 is not None
        assert f_mp4.mime_type == 'video/mp4'
        assert preview_service.get_preview_type(f_mp4) == 'video'

        f_bad = File.query.filter_by(original_filename='test_bad.mp3').first()
        assert f_bad is None

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
