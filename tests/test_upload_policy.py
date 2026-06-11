"""
Description: Pytest module covering upload policy.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import io

import pytest

from app.models.system_stat import SystemStat
from app.services.folder_service import folder_service
from app.services.upload_policy_service import upload_policy_service
from app.services.upload_service import upload_service


def test_custom_allowed_extension_is_accepted(app, db, test_user_factory, temp_storage):
    user = test_user_factory()
    folder = folder_service.get_user_root_folder(user)
    SystemStat.set_stat(upload_policy_service.CUSTOM_ALLOWED_KEY, ["md"])

    uploaded = upload_service.process_upload(
        user,
        folder,
        io.BytesIO(b"# Notes"),
        filename="notes.md",
    )

    assert uploaded.original_filename == "notes.md"
    assert uploaded.extension == "md"


def test_blocked_extension_wins_over_custom_allowed(app, db):
    SystemStat.set_stat(upload_policy_service.CUSTOM_BLOCKED_KEY, ["md"])

    with pytest.raises(ValueError, match="Blocked"):
        upload_policy_service.save_custom_allowed_extensions("md")


def test_upload_policy_normalizes_admin_input(app, db):
    upload_policy_service.save_policy(" .HEIC, md\nwebp ", "")

    policy = upload_policy_service.get_policy()

    assert "heic" in policy["custom_allowed"]
    assert "md" in policy["custom_allowed"]
    assert "webp" in policy["allowed"]


def test_upload_policy_save_rejects_conflicts_without_partial_update(app, db):
    upload_policy_service.save_policy("md", "")

    with pytest.raises(ValueError, match="Blocked"):
        upload_policy_service.save_policy("md", "md")

    policy = upload_policy_service.get_policy()
    assert "md" in policy["custom_allowed"]
    assert "md" not in policy["custom_blocked"]


def test_disabled_upload_policy_allows_unknown_extensions(app, db):
    SystemStat.set_stat(upload_policy_service.ENABLED_KEY, False)

    assert upload_policy_service.validate_extension("unlisted") == "unlisted"


def test_disabled_upload_policy_still_blocks_dangerous_extensions(app, db):
    SystemStat.set_stat(upload_policy_service.ENABLED_KEY, False)

    with pytest.raises(ValueError, match="blocked"):
        upload_policy_service.validate_extension("exe")
