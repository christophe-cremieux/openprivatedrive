"""
Description: Pytest module covering bootstrap.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from app.models.user import User
from app.services.bootstrap_service import bootstrap_service


def test_ensure_admin_user_creates_initial_admin(app, db):
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "strong-test-password"

    admin = bootstrap_service.ensure_admin_user(app)

    assert admin.username == "admin"
    assert admin.email == "admin@example.com"
    assert admin.is_admin is True
    assert User.query.filter_by(username="admin").count() == 1


def test_ensure_admin_user_is_idempotent(app, db):
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "strong-test-password"

    first_admin = bootstrap_service.ensure_admin_user(app)
    second_admin = bootstrap_service.ensure_admin_user(app)

    assert first_admin.id == second_admin.id
    assert User.query.filter_by(username="admin").count() == 1


def test_reset_admin_password_updates_existing_admin(app, db):
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "first-password"
    admin = bootstrap_service.ensure_admin_user(app)

    app.config["ADMIN_PASSWORD"] = "second-password"
    updated_admin = bootstrap_service.reset_admin_password(app)

    assert updated_admin.id == admin.id
    assert updated_admin.check_password("second-password") is True
    assert updated_admin.check_password("first-password") is False
