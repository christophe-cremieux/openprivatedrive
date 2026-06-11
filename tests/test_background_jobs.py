"""
Description: Pytest module covering background jobs.
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
from app.services.background_jobs import process_file_pipeline_job
from app.services.preview_service import preview_service

def test_pipeline_job_sequences_correctly(app, db, test_user_factory, monkeypatch):
    user = test_user_factory()
    file_rec = File(
        uuid='pipeline-uuid',
        owner_id=user.id,
        original_filename='test.docx',
        stored_filename='test.bin',
        mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        size_bytes=100,
        sha256_hash='hash',
        storage_path='path'
    )
    db.session.add(file_rec)
    db.session.commit()

    calls = []
    # We mock scan_virus_job to actually update the scan_status as the real one would
    def mock_scan_clean(fid, a):
        calls.append('scan')
        # Simulate background update in another session
        with a.app_context():
             from app.extensions import db as _db
             f = _db.session.get(File, fid)
             f.scan_status = 'clean'
             f.is_quarantined = False
             _db.session.commit()

    def mock_scan_infected(fid, a):
        calls.append('scan')
        with a.app_context():
             from app.extensions import db as _db
             f = _db.session.get(File, fid)
             f.scan_status = 'infected'
             f.is_quarantined = True
             _db.session.commit()

    monkeypatch.setattr("app.services.background_jobs.extract_text_job", lambda fid, a: calls.append('extract'))
    monkeypatch.setattr("app.services.background_jobs.process_office_preview_job", lambda fid, a: calls.append('preview'))

    with app.app_context():
        # Case 1: Clean file
        monkeypatch.setattr("app.services.background_jobs.scan_virus_job", mock_scan_clean)
        process_file_pipeline_job(file_rec.id, app)
        assert calls == ['scan', 'extract', 'preview']

        # Case 2: Infected file
        calls.clear()
        monkeypatch.setattr("app.services.background_jobs.scan_virus_job", mock_scan_infected)
        process_file_pipeline_job(file_rec.id, app)
        assert calls == ['scan']
