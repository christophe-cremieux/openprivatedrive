"""
Description: Pytest module covering password management.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.extensions import db as db_instance
from app.models.user import User
from app.models.password_reset_token import PasswordResetToken
from app.services.password_service import password_service
from app.api.services import api_service
from datetime import datetime, timedelta, timezone

@pytest.fixture
def test_users(db, test_user_factory):
    user = test_user_factory(username='test', email='test@example.com', password='test')
    admin = test_user_factory(username='admin', email='admin@example.com', password='adminpassword', is_admin=True)
    return user, admin

def test_password_validation(app):
    with app.app_context():
        # Policy is 12 chars
        assert password_service.validate_password("short")[0] is False
        assert password_service.validate_password("thisisalongenoughpassword")[0] is True
        assert password_service.validate_password("")[0] is False

def test_user_change_password(client, test_users, app):
    user, admin = test_users
    # Login manually
    client.post('/login', data={'username': 'test', 'password': 'test'})

    with app.app_context():
        user = db_instance.session.get(User, user.id)
        old_hash = user.password_hash

        # Change password
        response = client.post('/account/change-password', data={
            'current_password': 'test',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)

        assert b"Your password has been changed successfully" in response.data

        db_instance.session.refresh(user)
        assert user.password_hash != old_hash
        assert user.check_password('newpassword123') is True

        # API tokens should be revoked
        api_service.create_tokens(user)
        assert any(t.revoked_at is None for t in user.api_tokens)

        client.post('/account/change-password', data={
            'current_password': 'newpassword123',
            'new_password': 'anotherpassword123',
            'confirm_password': 'anotherpassword123'
        })

        db_instance.session.refresh(user)
        # Check refresh tokens are revoked
        assert all(t.revoked_at is not None for t in user.api_tokens if t.token_type == 'refresh')

def test_admin_create_reset_link(client, test_users, app):
    user, admin = test_users
    client.post('/login', data={'username': 'admin', 'password': 'adminpassword'})

    with app.app_context():
        user = db_instance.session.get(User, user.id)
        user_uuid = user.uuid

        response = client.post(f'/admin/users/{user_uuid}/reset-password', follow_redirects=True)
        assert b"password reset link" in response.data.lower()
        assert b"test" in response.data
        assert b"/reset-password/" in response.data

        token_record = PasswordResetToken.query.filter_by(user_id=user.id).first()
        assert token_record is not None
        assert token_record.used_at is None

def test_public_reset_password(client, test_users, app):
    user, admin = test_users
    with app.app_context():
        user = db_instance.session.get(User, user.id)
        raw_token, _ = password_service.generate_reset_token(user)

        # GET reset page
        response = client.get(f'/reset-password/{raw_token}')
        assert response.status_code == 200
        assert b"Reset Password" in response.data

        # POST new password
        response = client.post(f'/reset-password/{raw_token}', data={
            'new_password': 'resetpassword123',
            'confirm_password': 'resetpassword123'
        }, follow_redirects=True)

        assert b"Your password has been reset successfully" in response.data

        db_instance.session.refresh(user)
        assert user.check_password('resetpassword123') is True

        token_record = PasswordResetToken.query.filter_by(user_id=user.id).first()
        assert token_record.used_at is not None

        # Token cannot be reused
        response = client.get(f'/reset-password/{raw_token}', follow_redirects=True)
        assert b"Invalid or already used token" in response.data

def test_api_change_password(client, test_users, app):
    user, admin = test_users
    with app.app_context():
        user = db_instance.session.get(User, user.id)
        user.set_password('test')
        db_instance.session.commit()

        token_data = api_service.create_tokens(user)
        access_token = token_data['access_token']

        headers = {'Authorization': f'Bearer {access_token}'}

        # Success
        response = client.post('/api/v1/account/change-password', json={
            'current_password': 'test',
            'new_password': 'apinewpassword123',
            'confirm_password': 'apinewpassword123'
        }, headers=headers)

        assert response.status_code == 200
        assert b"Password changed successfully" in response.data

        db_instance.session.refresh(user)
        assert user.check_password('apinewpassword123') is True

        # Old token should be revoked
        response = client.get('/api/v1/me', headers=headers)
        assert response.status_code == 401

def test_admin_deactivate_reactivate(client, test_users, app):
    user, admin = test_users
    client.post('/login', data={'username': 'admin', 'password': 'adminpassword'})

    with app.app_context():
        user = db_instance.session.get(User, user.id)
        user_uuid = user.uuid

        # Deactivate
        client.post(f'/admin/users/{user_uuid}/deactivate', follow_redirects=True)
        db_instance.session.refresh(user)
        assert user.is_active is False

        # Reactivate
        client.post(f'/admin/users/{user_uuid}/reactivate', follow_redirects=True)
        db_instance.session.refresh(user)
        assert user.is_active is True


def test_inactive_user_cannot_login(client, test_users, app):
    user, admin = test_users
    with app.app_context():
        user = db_instance.session.get(User, user.id)
        user.is_active = False
        db_instance.session.commit()
        db_instance.session.remove()

    response = client.post('/login', data={
        'username': 'test',
        'password': 'test'
    }, follow_redirects=True)

    assert b"This account is deactivated" in response.data


def test_inactive_user_api_token_is_rejected(client, test_users, app):
    user, admin = test_users
    with app.app_context():
        user = db_instance.session.get(User, user.id)
        token_data = api_service.create_tokens(user)
        user.is_active = False
        db_instance.session.commit()
        db_instance.session.remove()

    response = client.get(
        '/api/v1/me',
        headers={'Authorization': f"Bearer {token_data['access_token']}"}
    )

    assert response.status_code == 401


def test_reset_password_rejects_inactive_user(client, test_users, app):
    user, admin = test_users
    with app.app_context():
        user = db_instance.session.get(User, user.id)
        raw_token, _ = password_service.generate_reset_token(user)
        user.is_active = False
        db_instance.session.commit()
        db_instance.session.remove()

    response = client.post(f'/reset-password/{raw_token}', data={
        'new_password': 'resetpassword123',
        'confirm_password': 'resetpassword123'
    }, follow_redirects=True)

    assert b"This account is deactivated" in response.data
