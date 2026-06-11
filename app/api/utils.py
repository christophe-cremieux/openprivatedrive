"""
Description: Utility helpers used by API routes.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from functools import wraps
from flask import request, jsonify, g
from app.api.services import api_service

def api_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authentication required", "code": "auth_required"}), 401

        token = auth_header.split(" ")[1]
        user = api_service.validate_token(token)

        if not user:
            return jsonify({"error": "Invalid or expired token", "code": "invalid_token"}), 401

        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def api_response(data=None, error=None, code=None, status=200, metadata=None):
    """Standardized API response format."""
    response = {"success": status < 400}
    if error:
        response["error"] = error
        if code:
            response["code"] = code
    if data is not None:
        response["data"] = data
    if metadata is not None:
        response["metadata"] = metadata

    return jsonify(response), status

def get_user_from_token():
    """Helper to get user from token without enforcing requirement."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(" ")[1]
    return api_service.validate_token(token)
