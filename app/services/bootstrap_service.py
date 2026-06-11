"""
Description: Service layer implementation for BootstrapService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os

from app.auth.services import auth_service
from app.extensions import db
from app.models.user import User


class BootstrapService:
    @staticmethod
    def ensure_admin_user(app) -> User | None:
        admin_username = app.config["ADMIN_USERNAME"]
        existing_admin = User.query.filter_by(username=admin_username).first()
        if existing_admin:
            return existing_admin

        admin_password = app.config["ADMIN_PASSWORD"]
        is_prod = os.environ.get("FLASK_ENV") == "production"
        if is_prod and admin_password == "admin123":
            raise RuntimeError("Default admin password blocked in production.")

        return auth_service.create_user(
            username=admin_username,
            email=f"{admin_username}@example.com",
            password=admin_password,
            is_admin=True,
        )

    @staticmethod
    def reset_admin_password(app) -> User:
        admin_username = app.config["ADMIN_USERNAME"]
        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            admin = BootstrapService.ensure_admin_user(app)
            if admin is None:
                raise RuntimeError("Admin user could not be created.")
            return admin

        admin_password = app.config["ADMIN_PASSWORD"]
        is_prod = os.environ.get("FLASK_ENV") == "production"
        if is_prod and admin_password == "admin123":
            raise RuntimeError("Default admin password blocked in production.")

        admin.set_password(admin_password)
        db.session.commit()
        return admin


bootstrap_service = BootstrapService()
