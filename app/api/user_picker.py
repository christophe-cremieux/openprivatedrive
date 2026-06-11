"""
Description: Implements user picker helper functionality for API endpoints.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from flask import Blueprint, request, g
from app.extensions import db, limiter
from app.api.utils import api_required, api_response
from app.models.user import User

user_picker_api = Blueprint("user_picker_api", __name__, url_prefix="/api/v1")

@user_picker_api.route("/users/search")
@api_required
@limiter.limit("50 per minute")
def search_users():
    query = request.args.get("q", "")
    if len(query) < 2:
        return api_response(data=[])

    # Search by username or email, excluding the current user
    users = User.query.filter(
        (User.username.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%"))
    ).filter(User.id != g.current_user.id).limit(10).all()

    results = []
    for u in users:
        results.append({
            "username": u.username,
            "email": u.email
        })

    return api_response(data=results)
