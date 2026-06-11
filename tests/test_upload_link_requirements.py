"""
Description: Pytest module covering upload link requirements.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.public_links.services import public_link_service
from app.auth.services import auth_service
from app.services.folder_service import folder_service

def test_upload_link_requirements(app, db, temp_storage):
    with app.app_context():
        user = auth_service.create_user("upload_link_test", "ul@ex.com", "pass")
        root = folder_service.get_user_root_folder(user)

        # Should fail without password
        with pytest.raises(ValueError, match="Password is required for upload links"):
            public_link_service.create_public_link(user, root, link_type='upload')

        # Should fail with invalid max_files
        with pytest.raises(ValueError, match="Valid max files limit is required"):
            public_link_service.create_public_link(user, root, link_type='upload', password='pass', max_files=0)

        # Should pass with all requirements
        token, link = public_link_service.create_public_link(
            user, root, link_type='upload', password='pass', max_files=10, max_upload_size_mb=50
        )
        assert link.link_type == 'upload'
        assert link.password_required is True
        assert link.max_files == 10
        assert link.max_upload_size_mb == 50
