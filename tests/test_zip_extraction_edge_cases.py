"""
Description: Pytest module covering zip extraction edge cases.
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
import stat
from app.extensions import db
from app.models.file import File
from app.models.folder import Folder
from app.models.zip_extract_job import ZipExtractJob
from app.services.zip_extract_service import zip_extract_service
from app.services.upload_service import upload_service
from app.api.services import api_service

def create_test_zip_custom(entries):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zf:
        for entry in entries:
            name = entry['name']
            content = entry.get('content', b'')
            info = zipfile.ZipInfo(name)
            if 'external_attr' in entry:
                info.external_attr = entry['external_attr']
            zf.writestr(info, content)
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

def test_zip_extraction_windows_paths(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    # Create ZIP with backslashes
    zip_content = create_test_zip_custom([
        {'name': 'folder1\\file1.txt', 'content': b'c1'}
    ])
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='win.zip')
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'completed'
    assert job.summary_json['files_created'] == 1

    f1 = Folder.query.filter_by(name='folder1', parent_id=root_folder.id).first()
    assert f1 is not None
    assert File.query.filter_by(original_filename='file1.txt', folder_id=f1.id).first() is not None

def test_zip_extraction_bomb_ratio(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    app.config['ZIP_EXTRACT_MAX_RATIO'] = 10

    # Create a highly compressible file
    large_content = b'0' * 10000
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('bomb.txt', large_content)
    zip_buffer.seek(0)

    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_buffer, filename='bomb.zip')
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'completed_with_errors'
    assert job.summary_json['files_skipped'] == 1
    assert any("ratio" in err.lower() for err in job.summary_json['errors'])

def test_zip_extraction_quarantined_zip(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    zip_content = create_test_zip_custom([{'name': 'f.txt', 'content': b'1'}])
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='q.zip')
    zip_file.is_quarantined = True
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'failed'
    assert "quarantined" in job.error_message.lower()

def test_zip_extraction_duplicate_skip(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

    # Create an existing file
    upload_service.process_upload(user, root_folder, b'existing', filename='dup.txt')
    db.session.commit()

    zip_content = create_test_zip_custom([{'name': 'dup.txt', 'content': b'new'}])
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='dup.zip')
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'completed_with_errors'
    assert job.summary_json['files_skipped'] == 1
    assert any("already exists" in err for err in job.summary_json['errors'])

def test_zip_extraction_symlink_block(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

    # Create ZIP with symlink entry
    zip_content = create_test_zip_custom([
        {'name': 'link.txt', 'content': b'target.txt', 'external_attr': 0o120000 << 16}
    ])
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='sym.zip')
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'completed_with_errors'
    assert job.summary_json['files_skipped'] == 1
    assert any("symlink" in err.lower() for err in job.summary_json['errors'])

def test_zip_extraction_path_component_traversal(client, test_user_factory, db, temp_storage, app):
    user = test_user_factory()
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

    # Create ZIP with ambiguous .. in path
    zip_content = create_test_zip_custom([
        {'name': 'folder/../traversal.txt', 'content': b'content'}
    ])
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='traversal.zip')
    db.session.commit()

    job = ZipExtractJob(user_id=user.id, zip_file_id=zip_file.id, destination_folder_id=root_folder.id)
    db.session.add(job)
    db.session.commit()

    zip_extract_service.extract_zip_background(job.uuid, app=app)

    db.session.expire_all()
    job = ZipExtractJob.query.filter_by(uuid=job.uuid).first()
    assert job.status == 'completed_with_errors'
    assert job.summary_json['files_skipped'] == 1
    assert any("traversal component" in err.lower() for err in job.summary_json['errors'])

def test_zip_wrapper_folder_collision(client, auth_helper, test_user_factory, db, temp_storage):
    user = test_user_factory()
    auth_helper.login()
    root_folder = Folder.query.filter_by(owner_id=user.id, is_root=True).first()

    # Create a folder that will collide
    from app.services.folder_service import folder_service
    folder_service.create_folder(user, root_folder, "test")
    db.session.commit()

    # Create and upload ZIP
    zip_content = create_test_zip_custom([{'name': 'f1.txt', 'content': b'1'}])
    zip_file = upload_service.process_upload(user, root_folder, zip_content, filename='test.zip')
    db.session.commit()

    # Trigger via API
    response = client.post(f'/api/v1/files/{zip_file.uuid}/extract-zip', json={
        'extract_into_named_folder': True
    }, headers=auth_helper.get_auth_header(user))

    assert response.status_code == 202

    # Check if a new folder "test (1)" was created
    new_folder = Folder.query.filter_by(name="test (1)", parent_id=root_folder.id).first()
    assert new_folder is not None
