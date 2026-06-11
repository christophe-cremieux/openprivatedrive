"""
Description: Pytest module covering zip extraction.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import io
import zipfile
import pytest
from app.extensions import db
from app.models.file import File
from app.models.folder import Folder
from app.models.zip_extract_job import ZipExtractJob
from app.services.zip_extract_service import zip_extract_service
from app.services.upload_service import upload_service
from app.api.services import api_service

def create_test_zip(files_dict):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name, content in files_dict.items():
            zip_file.writestr(file_name, content)
    zip_buffer.seek(0)
    return zip_buffer

@pytest.fixture
def auth_helper(client):
    class AuthHelper:
        def login(self, username="authuser", password="password"):
            return client.post("/login", data={
                "username": username,
                "password": password
            })
        def get_auth_header(self, user):
            tokens = api_service.create_tokens(user)
            return {"Authorization": f"Bearer {tokens['access_token']}"}
    return AuthHelper()

def test_zip_extraction_success(client, test_user_factory, auth_helper, db, temp_storage, app):
    user = test_user_factory()
    auth_helper.login()

    # 1. Create and upload a ZIP file
    zip_content = create_test_zip({
        'file1.txt': b'content1',
        'folder1/file2.txt': b'content2'
    })

    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='test.zip')
    db.session.commit()

    # 2. Trigger extraction via API
    response = client.post(f'/api/v1/files/{zip_file.uuid}/extract-zip', json={
        'extract_into_named_folder': True
    }, headers=auth_helper.get_auth_header(user))

    assert response.status_code == 202
    job_uuid = response.get_json()['data']['job_uuid']

    # 3. Run background task manually
    zip_extract_service.extract_zip_background(job_uuid, app=app)

    # 4. Verify results
    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job_uuid).first()
    assert job.status == 'completed'
    assert job.summary_json['files_created'] == 2
    assert job.summary_json['folders_created'] >= 1

    # Check if files exist in DB
    extracted_folder = Folder.query.filter_by(name='test', parent_id=root_folder.id).first()
    assert extracted_folder is not None

    f1 = File.query.filter_by(original_filename='file1.txt', folder_id=extracted_folder.id).first()
    assert f1 is not None

    subfolder = Folder.query.filter_by(name='folder1', parent_id=extracted_folder.id).first()
    assert subfolder is not None

    f2 = File.query.filter_by(original_filename='file2.txt', folder_id=subfolder.id).first()
    assert f2 is not None

def test_zip_extraction_path_traversal(client, test_user_factory, auth_helper, db, temp_storage, app):
    user = test_user_factory()
    auth_helper.login()

    zip_content = create_test_zip({
        '../traversal.txt': b'dangerous'
    })

    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='evil.zip')
    db.session.commit()

    response = client.post(f'/api/v1/files/{zip_file.uuid}/extract-zip', json={
        'extract_into_named_folder': False
    }, headers=auth_helper.get_auth_header(user))

    job_uuid = response.get_json()['data']['job_uuid']
    zip_extract_service.extract_zip_background(job_uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job_uuid).first()
    assert job.summary_json['files_skipped'] == 1
    assert any("traversal" in err for err in job.summary_json['errors'])

def test_zip_extraction_limits(client, test_user_factory, auth_helper, db, temp_storage, app):
    user = test_user_factory()
    auth_helper.login()

    app.config['ZIP_EXTRACT_MAX_FILES'] = 2

    zip_content = create_test_zip({
        'f1.txt': b'1',
        'f2.txt': b'2',
        'f3.txt': b'3'
    })

    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='limit.zip')
    db.session.commit()

    response = client.post(f'/api/v1/files/{zip_file.uuid}/extract-zip', json={
        'extract_into_named_folder': False
    }, headers=auth_helper.get_auth_header(user))

    job_uuid = response.get_json()['data']['job_uuid']
    zip_extract_service.extract_zip_background(job_uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job_uuid).first()
    assert job.status == 'failed'
    assert "too many items" in job.error_message

def test_zip_extraction_permissions(client, test_user_factory, auth_helper, db, temp_storage):
    user = test_user_factory(username="u1", email="u1@e.com")
    second_user = test_user_factory(username="u2", email="u2@e.com")

    zip_content = create_test_zip({'f1.txt': b'1'})
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='perm.zip')
    db.session.commit()

    response = client.post(f'/api/v1/files/{zip_file.uuid}/extract-zip', json={
        'extract_into_named_folder': False
    }, headers=auth_helper.get_auth_header(second_user))

    assert response.status_code == 403
