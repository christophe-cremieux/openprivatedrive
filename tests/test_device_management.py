"""
Description: Pytest module covering device management.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import pytest
from app.auth.services import auth_service
from app.api.services import api_service

def test_device_management(client, app, db):
    with app.app_context():
        user = auth_service.create_user("deviceuser", "dev@ex.com", "password")
        token_data1 = api_service.create_tokens(user, "dev1", "Phone")
        token_data2 = api_service.create_tokens(user, "dev2", "Tablet")

        acc1 = token_data1['access_token']

        # 1. List devices
        response = client.get("/api/v1/devices", headers={"Authorization": f"Bearer {acc1}"})
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert len(data) == 2

        dev2_uuid = next(d["uuid"] for d in data if d["device_id"] == "dev2")

        # 2. Revoke device 2
        response = client.delete(f"/api/v1/devices/{dev2_uuid}", headers={"Authorization": f"Bearer {acc1}"})
        assert response.status_code == 200

        # 3. List devices again
        response = client.get("/api/v1/devices", headers={"Authorization": f"Bearer {acc1}"})
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert len(data) == 1
        assert data[0]["device_id"] == "dev1"

        # 4. Try to use token from device 2 (should be revoked)
        acc2 = token_data2['access_token']
        response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {acc2}"})
        assert response.status_code == 401
