"""
Description: Pytest module covering signature validation.
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
import zipfile
from app.services.upload_service import upload_service
from app.auth.services import auth_service
from app.services.folder_service import folder_service

def create_mock_office_file(type='word'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        if type == 'word':
            zf.writestr('word/document.xml', 'content')
        elif type == 'excel':
            zf.writestr('xl/workbook.xml', 'content')
        elif type == 'ppt':
            zf.writestr('ppt/presentation.xml', 'content')
        zf.writestr('[Content_Types].xml', 'types')
    return buf.getvalue()

def test_signature_validation(app, db, temp_storage):
    with app.app_context():
        user = auth_service.create_user("sig_test", "sig@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)

        # Valid PNG
        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 10
        upload_service.process_upload(user, root, png_data, "test.png")

        # Invalid PNG (signature is PDF)
        fake_png = b'%PDF-1.4\n' + b'\x00' * 10
        with pytest.raises(ValueError, match="File signature mismatch"):
            upload_service.process_upload(user, root, fake_png, "fake.png")

        # Valid PDF
        pdf_data = b'%PDF-1.4\n' + b'\x00' * 10
        upload_service.process_upload(user, root, pdf_data, "test.pdf")

        # Valid Office doc
        docx_data = create_mock_office_file('word')
        upload_service.process_upload(user, root, docx_data, "test.docx")

        # Invalid Office doc (just ZIP signature, no Office content)
        fake_docx = b'PK\x03\x04' + b'\x00' * 20 # Not a valid ZIP either
        with pytest.raises(ValueError, match="not a valid ZIP"):
            upload_service.process_upload(user, root, fake_docx, "fake.docx")

        # Valid ZIP (not Office)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('test.txt', 'hello')
        zip_data = buf.getvalue()
        upload_service.process_upload(user, root, zip_data, "test.zip")
