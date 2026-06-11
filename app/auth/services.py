"""
Description: Provides authentication business logic and helper services.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from app.extensions import db
from app.models.user import User
from app.services.folder_service import folder_service

class AuthService:
    @staticmethod
    def create_user(username, email, password, is_admin=False):
        user = User(username=username, email=email, is_admin=is_admin)
        user.set_password(password)
        db.session.add(user)
        # Use flush to get the user ID without committing yet
        db.session.flush()

        # Create user's root folder
        folder_service.create_root_folder_for_user(user)

        db.session.commit()

        return user

auth_service = AuthService()
