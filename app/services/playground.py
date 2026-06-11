"""
Description: Implements service layer logic for playground.
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
from app.auth.services import auth_service

def seed_test_users():
    test_users = [
        {"username": "jimmy", "email": "jimmy@example.com"},
        {"username": "oscar", "email": "oscar@example.com"},
        {"username": "sammy", "email": "sammy@example.com"},
    ]

    for user_data in test_users:
        if not User.query.filter_by(username=user_data["username"]).first():
            auth_service.create_user(
                username=user_data["username"],
                email=user_data["email"],
                password="123"
            )
            print(f"Created test user: {user_data['username']}")
