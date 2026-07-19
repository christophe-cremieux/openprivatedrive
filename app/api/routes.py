"""
Description: Defines API endpoints for external client access and JSON responses.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
from flask import Blueprint, request, g, send_file, url_for, current_app
from app.extensions import db, limiter
from app.api.utils import api_required, api_response
from app.api.services import api_service
from app.services.password_service import password_service
from app.services.activity_log_service import activity_log_service
from app.services.preview_service import preview_service
from app.services.encryption_service import encryption_service
from app.models.user import User
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.upload_service import upload_service
from app.services.upload_session_service import upload_session_service
from app.services.storage_service import storage_service
from app.sharing.services import sharing_service
from app.public_links.services import public_link_service
from app.sync.services import sync_service
from app.services.zip_extract_service import zip_extract_service
from app.models.folder import Folder
from app.models.file import File
from app.models.zip_extract_job import ZipExtractJob
from app.models.api_token import ApiToken
from app.models.upload_session import UploadSession
from app.drive.permissions import can_access
from datetime import datetime, timedelta, timezone

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# --- Auth Endpoints ---

@api_v1.route("/auth/login", methods=["POST"])
@limiter.limit("10 per minute", on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    device_id = data.get("device_id")
    device_name = data.get("device_name")

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        if user:
            activity_log_service.log_activity(user.id, 'api_failed_login')
        return api_response(error="Invalid username or password", code="invalid_credentials", status=401)

    if not user.is_active:
        activity_log_service.log_activity(user.id, 'api_failed_login_inactive')
        return api_response(error="Account is deactivated", code="account_deactivated", status=403)

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    token_data = api_service.create_tokens(user, device_id, device_name)
    activity_log_service.log_activity(user.id, 'api_login', metadata={'device_id': device_id})

    return api_response(data={
        **token_data,
        "user": {
            "uuid": user.uuid,
            "username": user.username,
            "email": user.email
        }
    })

@api_v1.route("/auth/refresh", methods=["POST"])
@limiter.limit("20 per minute", on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def refresh():
    data = request.get_json()
    refresh_token = data.get("refresh_token")

    token_data = api_service.refresh_access_token(refresh_token)
    if not token_data:
        return api_response(error="Invalid or expired refresh token", code="invalid_refresh_token", status=401)

    return api_response(data=token_data)

@api_v1.route("/auth/logout", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def logout():
    data = request.get_json() or {}
    device_id = data.get("device_id")
    api_service.revoke_tokens(g.current_user, device_id)
    activity_log_service.log_activity(g.current_user.id, 'api_logout', metadata={'device_id': device_id})
    return api_response(data={"message": "Logged out successfully"})

@api_v1.route("/capabilities")
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def capabilities():
    from sqlalchemy import func
    from app.services.activity_log_service import activity_log_service
    from flask_login import current_user
    from app.models.system_stat import SystemStat

    storage_used = 0
    storage_limit = 0
    user = None
    if current_user.is_authenticated:
        user = current_user
    elif 'Authorization' in request.headers:
        # Try to get user from token for mobile clients
        from app.api.utils import get_user_from_token
        user = get_user_from_token()

    if user:
        storage_limit = user.storage_quota_bytes
        # Get usage
        usage_data = db.session.query(func.sum(File.size_bytes)).filter(
            File.owner_id == user.id,
            File.is_deleted == False
        ).scalar() or 0
        storage_used = usage_data

    from app.services.upload_policy_service import upload_policy_service
    upload_policy = upload_policy_service.get_policy()

    global_limit_mb = SystemStat.get_stat('global_max_upload_size_mb', 0)
    server_limit_mb = current_app.config.get("MAX_CONTENT_LENGTH", 100 * 1024 * 1024) // (1024 * 1024)
    effective_limit_mb = global_limit_mb if global_limit_mb > 0 else server_limit_mb

    return api_response(data={
        "max_upload_size_mb": effective_limit_mb,
        "storage_used_bytes": storage_used,
        "storage_limit_bytes": storage_limit,
        "allowed_extensions": upload_policy["allowed"],
        "blocked_extensions": upload_policy["blocked"],
        "preview_types": ["image", "pdf", "text", "csv", "video", "audio", "office_pdf"],
        "encryption_supported": current_app.config.get("ENCRYPTED_FILES_ENABLED", True),
        "resumable_upload_supported": True,
        "resumable_encrypted_upload_supported": False,
        "quarantine_scan_enabled": True,
        "office_preview_enabled": current_app.config.get("OFFICE_PREVIEW_ENABLED", False),
        "office_preview_max_mb": current_app.config.get("OFFICE_PREVIEW_MAX_MB", 50),
        "max_chunk_size": upload_session_service.MAX_CHUNK_SIZE,
        "encryption_min_password_length": current_app.config.get("ENCRYPTION_MIN_PASSWORD_LENGTH", 12),
        "thumbnail_sizes": ["small", "large"],
        "unsupported_encrypted_features": ["preview", "search_content", "public_sharing"],
        "public_link_encrypted_supported": False,
        "zip_export_max_mb": current_app.config.get("ZIP_EXPORT_MAX_MB", 250)
    })

@api_v1.route("/account/change-password", methods=["POST"])
@api_required
@limiter.limit("5 per minute")
def api_change_password():
    data = request.get_json() or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        return api_response(error="Missing required fields", status=400)

    if not g.current_user.check_password(current_password):
        return api_response(error="Current password is incorrect", code="invalid_password", status=401)

    if new_password != confirm_password:
        return api_response(error="New passwords do not match", status=400)

    if current_password == new_password:
        return api_response(error="New password must be different from the current password", status=400)

    is_valid, error_msg = password_service.validate_password(new_password)
    if not is_valid:
        return api_response(error=error_msg, status=400)

    g.current_user.set_password(new_password)

    # Revoke all tokens except current one?
    # Usually for API, we might want to revoke everything including the current access token
    # so the user has to re-login on the device.
    api_service.revoke_tokens(g.current_user)

    db.session.commit()

    activity_log_service.log_activity(g.current_user.id, 'api_password_changed')
    return api_response(data={"message": "Password changed successfully. Please log in again."})

@api_v1.route("/me")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def me():
    user = g.current_user
    return api_response(data={
        "uuid": user.uuid,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "storage_quota_bytes": user.storage_quota_bytes
    })

# --- Trash Endpoints ---

@api_v1.route("/trash")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_trash():
    top_deleted_folders = folder_service.get_trash_items(g.current_user)
    top_deleted_files = file_service.get_trash_items(g.current_user)

    items = []
    for f in top_deleted_folders:
        items.append({
            "uuid": f.uuid,
            "type": "folder",
            "name": f.name,
            "deleted_at": f.deleted_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if f.deleted_at else None
        })
    for f in top_deleted_files:
        items.append({
            "uuid": f.uuid,
            "type": "file",
            "name": f.original_filename,
            "deleted_at": f.deleted_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if f.deleted_at else None
        })

    return api_response(data=items)

@api_v1.route("/trash/empty", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_empty_trash():
    folder_service.empty_trash(g.current_user)
    return api_response(data={"message": "Trash emptied"})

@api_v1.route("/folders/<folder_uuid>/restore", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_restore_folder(folder_uuid):
    folder = folder_service.get_deleted_folder_by_uuid(folder_uuid, g.current_user)
    if not folder:
        return api_response(error="Folder not found in trash", status=404)
    folder_service.restore_folder(g.current_user, folder)
    return api_response(data={"message": "Folder restored"})

@api_v1.route("/files/<file_uuid>/restore", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_restore_file(file_uuid):
    file_record = file_service.get_deleted_file_by_uuid(file_uuid, g.current_user)
    if not file_record:
        return api_response(error="File not found in trash", status=404)
    file_service.restore_file(g.current_user, file_record)
    return api_response(data={"message": "File restored"})

# --- Folder Endpoints ---

@api_v1.route("/folders/root")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_root_folder():
    folder = folder_service.get_user_root_folder(g.current_user)
    return api_response(data={
        "uuid": folder.uuid,
        "name": folder.name,
        "type": "folder",
        "is_root": True,
        "is_starred": folder.is_starred,
        "updated_at": folder.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
    })

@api_v1.route("/folders/<folder_uuid>/path")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_folder_path(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='view')
        if not folder:
            return api_response(error="Folder not found", status=404)

        path = folder_service.get_path(folder)
        return api_response(data=path)
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/folders/<folder_uuid>")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='view')
        if not folder:
            return api_response(error="Folder not found", status=404)
    except PermissionError as e:
        return api_response(error=str(e), status=403)

    from app.drive.permissions import get_effective_permission

    # Sorting
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    result = folder_service.list_folder_contents_paginated(
        g.current_user, folder, page=page, per_page=per_page, sort_by=sort_by, order=order
    )

    return api_response(data={
        "uuid": folder.uuid,
        "name": folder.name,
        "parent_uuid": folder.parent.uuid if folder.parent else None,
        "encrypt_new_uploads": folder.encrypt_new_uploads,
        "items": result["items"],
        "pagination": result["pagination"]
    })

@api_v1.route("/folders", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def create_folder():
    data = request.get_json()
    name = data.get("name")
    parent_uuid = data.get("parent_uuid")

    if not name:
        return api_response(error="Folder name required", status=400)

    try:
        parent = None
        if parent_uuid:
            parent = folder_service.get_folder_by_uuid(parent_uuid, user=g.current_user, action='upload')
            if not parent:
                return api_response(error="Parent folder not found", status=404)
        else:
            parent = folder_service.get_user_root_folder(g.current_user)

        new_folder = folder_service.create_folder(g.current_user, parent, name)
        return api_response(data={
            "uuid": new_folder.uuid,
            "name": new_folder.name,
            "type": "folder",
            "is_starred": new_folder.is_starred,
            "updated_at": new_folder.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        }, status=201)
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/folders/<folder_uuid>/move", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def move_folder(folder_uuid):
    data = request.get_json()
    dest_uuid = data.get("destination_uuid")
    if not dest_uuid:
        return api_response(error="destination_uuid required", status=400)

    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='move')
        if not folder:
            return api_response(error="Folder not found", status=404)

        dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=g.current_user, action='upload')
        if not dest_folder:
            return api_response(error="Destination folder not found", status=404)

        folder_service.move_folder(g.current_user, folder, dest_folder)
        return api_response(data={"message": "Folder moved successfully"})
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/folders/<folder_uuid>/copy", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def copy_folder(folder_uuid):
    data = request.get_json()
    dest_uuid = data.get("destination_uuid")
    if not dest_uuid:
        return api_response(error="destination_uuid required", status=400)

    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='view')
        if not folder:
            return api_response(error="Folder not found", status=404)

        dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=g.current_user, action='upload')
        if not dest_folder:
            return api_response(error="Destination folder not found", status=404)

        new_folder = folder_service.copy_folder(g.current_user, folder, dest_folder)
        return api_response(data={
            "uuid": new_folder.uuid,
            "name": new_folder.name,
            "type": "folder",
            "is_starred": new_folder.is_starred,
            "updated_at": new_folder.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        }, status=201)
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/folders/<folder_uuid>", methods=["PATCH"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def patch_folder(folder_uuid):
    data = request.get_json()
    new_name = data.get("name")
    encrypt_new_uploads = data.get("encrypt_new_uploads")

    try:
        # Check permissions - rename requires 'rename', policy change requires 'edit'
        # To handle both in one PATCH, we check for 'edit' as it's generally what's needed for policy
        action = 'rename' if new_name and not encrypt_new_uploads else 'edit'
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action=action)
        if not folder:
            return api_response(error="Folder not found", status=404)

        if folder.is_root and new_name:
            return api_response(error="Cannot rename root folder", status=400)

        if new_name:
            folder_service.rename_folder(g.current_user, folder, new_name)

        if encrypt_new_uploads is not None:
            folder.encrypt_new_uploads = bool(encrypt_new_uploads)
            db.session.commit()

        return api_response(data={
            "uuid": folder.uuid,
            "name": folder.name,
            "type": "folder",
            "is_starred": folder.is_starred,
            "updated_at": folder.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            "encrypt_new_uploads": folder.encrypt_new_uploads
        })
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/files/<file_uuid>/move", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def move_file(file_uuid):
    data = request.get_json()
    dest_uuid = data.get("destination_uuid")
    if not dest_uuid:
        return api_response(error="destination_uuid required", status=400)

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='move')
        if not file_record:
            return api_response(error="File not found", status=404)

        dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=g.current_user, action='upload')
        if not dest_folder:
            return api_response(error="Destination folder not found", status=404)

        file_service.move_file(g.current_user, file_record, dest_folder)
        return api_response(data={"message": "File moved successfully"})
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/files/<file_uuid>/copy", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def copy_file(file_uuid):
    data = request.get_json()
    dest_uuid = data.get("destination_uuid")
    if not dest_uuid:
        return api_response(error="destination_uuid required", status=400)

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)

        dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=g.current_user, action='upload')
        if not dest_folder:
            return api_response(error="Destination folder not found", status=404)

        new_file = file_service.copy_file(g.current_user, file_record, dest_folder)
        return api_response(data={
            "uuid": new_file.uuid,
            "name": new_file.original_filename,
            "type": "file",
            "mime_type": new_file.mime_type,
            "size": new_file.size_bytes,
            "is_starred": new_file.is_starred,
            "updated_at": new_file.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        }, status=201)
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/folders/<folder_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def delete_folder(folder_uuid):
    permanent = request.args.get("permanent", "false").lower() == "true"
    try:
        folder_service.delete_folder(g.current_user, folder_uuid, permanent=permanent)
        message = "Folder permanently deleted" if permanent else "Folder deleted successfully"
        return api_response(data={"message": message})
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        return api_response(error=str(e), status=status)

# --- File & Upload Endpoints ---

@api_v1.route("/uploads/session", methods=["POST"])
@api_required
@limiter.limit("50 per hour", on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def create_upload_session():
    data = request.get_json()

    if data.get("is_encrypted") == True or data.get("is_encrypted") == "true":
        return api_response(error="Encryption is not supported for resumable uploads in this version.", status=400)

    try:
        session = upload_session_service.create_session(
            g.current_user,
            data.get("filename"),
            data.get("total_size"),
            data.get("total_chunks"),
            data.get("sha256"),
            data.get("folder_uuid"),
            data.get("relative_path")
        )
        return api_response(data={
            "session_uuid": session.uuid,
            "completed_chunks": session.completed_chunks or []
        }, status=201)
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/uploads/session/<session_uuid>/chunks/<int:chunk_index>", methods=["PUT"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def upload_chunk(session_uuid, chunk_index):
    session = upload_session_service.get_session(session_uuid, g.current_user)
    if not session:
        return api_response(error="Session not found or inactive", status=404)

    try:
        upload_session_service.save_chunk(session, chunk_index, request.get_data())
        return api_response(data={"message": f"Chunk {chunk_index} uploaded"})
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/uploads/session/<session_uuid>")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_upload_session_status(session_uuid):
    session = upload_session_service.get_session(session_uuid, g.current_user)
    if not session:
        return api_response(error="Session not found or inactive", status=404)

    return api_response(data={
        "uuid": session.uuid,
        "filename": session.filename,
        "total_size": session.total_size,
        "total_chunks": session.total_chunks,
        "completed_chunks": session.completed_chunks,
        "status": session.status,
        "expires_at": session.expires_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
    })

@api_v1.route("/uploads/session/<session_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def cancel_upload_session(session_uuid):
    success = upload_session_service.cancel_session(session_uuid, g.current_user)
    if not success:
        return api_response(error="Session not found", status=404)

    return api_response(data={"message": "Upload session cancelled and cleaned up"})

@api_v1.route("/uploads/session/<session_uuid>/complete", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def complete_upload_session(session_uuid):
    session = upload_session_service.get_session(session_uuid, g.current_user)
    if not session:
        return api_response(error="Session not found or inactive", status=404)

    try:
        new_file = upload_session_service.finalize_session(session, g.current_user)
        return api_response(data={
            "uuid": new_file.uuid,
            "name": new_file.original_filename,
            "type": "file",
            "mime_type": new_file.mime_type,
            "size": new_file.size_bytes,
            "is_starred": new_file.is_starred,
            "updated_at": new_file.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        }, status=201)
    except ValueError as e:
        return api_response(error=str(e), status=400)
    except Exception as e:
        return api_response(error=f"Failed to complete upload: {str(e)}", status=500)

@api_v1.route("/files/upload", methods=["POST"])
@api_required
@limiter.limit("100 per hour", on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def upload_file():
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return api_response(error="No files provided", status=400)

    folder_uuid = request.form.get("folder_uuid")
    prefix = request.form.get("prefix")
    relative_paths = request.form.getlist("relative_paths[]")
    is_encrypted = request.form.get("is_encrypted") == "true"
    password = request.form.get("password")

    try:
        folder = None
        if folder_uuid:
            folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='upload')
            if not folder:
                return api_response(error="Folder not found", status=404)
        else:
            folder = folder_service.get_user_root_folder(g.current_user)

        if len(files) == 1 and not prefix and not relative_paths:
            custom_name = request.form.get("custom_name")
            new_file = upload_service.process_upload(
                g.current_user, folder, files[0],
                filename=custom_name,
                is_encrypted=is_encrypted,
                password=password
            )
            db.session.commit()
            return api_response(data={"uuid": new_file.uuid, "name": new_file.original_filename}, status=201)
        else:
            uploaded, errors = upload_service.process_bulk_upload(
                g.current_user, folder, files,
                prefix=prefix,
                relative_paths=relative_paths,
                is_encrypted=is_encrypted,
                password=password
            )

            if errors and not uploaded:
                return api_response(error="Upload failed", metadata={"errors": errors}, status=400)

            return api_response(data=[{"uuid": f.uuid, "name": f.original_filename} for f in uploaded],
                               metadata={"errors": errors} if errors else None,
                               status=201 if uploaded else 200)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/files/<file_uuid>")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_file_metadata(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)
    except PermissionError as e:
        return api_response(error=str(e), status=403)

    return api_response(data={
        "uuid": file_record.uuid,
        "name": file_record.original_filename,
        "size": file_record.size_bytes,
        "mime_type": file_record.mime_type,
        "hash": file_record.sha256_hash,
        "is_encrypted": file_record.is_encrypted,
        "scan_status": file_record.scan_status,
        "is_quarantined": file_record.is_quarantined,
        "previewable": preview_service.is_previewable(file_record),
        "preview_type": preview_service.get_preview_type(file_record),
        "searchable_content": not file_record.is_encrypted,
        "requires_password_for_download": file_record.is_encrypted,
        "created_at": file_record.created_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
        "updated_at": file_record.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
        "deleted_at": file_record.deleted_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if file_record.deleted_at else None,
        "server_modified_at": file_record.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
        "etag": file_record.sha256_hash,
        "sync_state": "synced" if not file_record.is_deleted else "deleted",
        "capabilities": {
            "can_preview": preview_service.is_previewable(file_record) and not file_record.is_encrypted,
            "can_download": True,
            "can_share": not file_record.is_encrypted,
            "requires_password": file_record.is_encrypted
        }
    })

@api_v1.route("/files/<file_uuid>/download")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def download_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='download')
        if not file_record:
            return api_response(error="File not found", status=404)

        if file_record.is_encrypted:
            return api_response(error="File is encrypted. Use decrypt-download endpoint.", code="file_encrypted", status=403)

    except PermissionError as e:
        return api_response(error=str(e), status=403)

    # Security: Ensure path traversal protection
    if not storage_service.is_safe_path(file_record.storage_path):
        return api_response(error="Permission denied", status=403)

    full_path = storage_service.get_full_path(file_record.storage_path)
    if not os.path.exists(full_path):
        return api_response(error="File data missing from storage", status=404)

    return send_file(full_path, as_attachment=True, download_name=file_record.original_filename)

@api_v1.route("/files/<file_uuid>/decrypt-download", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("DECRYPT_RATE_LIMIT", "5 per minute"))
def api_decrypt_download(file_uuid):
    data = request.get_json(silent=True) or {}
    password = data.get("password")

    if not password:
        return api_response(error="Password is required", status=400)

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='download')
        if not file_record:
            return api_response(error="File not found", status=404)

        if not file_record.is_encrypted:
            return api_response(error="File is not encrypted", status=400)

        # Security: Ensure path traversal protection
        if not storage_service.is_safe_path(file_record.storage_path):
            return api_response(error="Permission denied", status=403)

        full_path = storage_service.get_full_path(file_record.storage_path)
        if not os.path.exists(full_path):
            return api_response(error="File data missing", status=404)

        import tempfile
        # Decrypt to a temporary file first to verify the password (GCM tag)
        # and ensure we can return a proper 401 if it fails.
        temp_dir = os.path.join(current_app.config['STORAGE_PATH'], 'temp')
        os.makedirs(temp_dir, mode=0o700, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, prefix="decrypt_")
        tmp_path = tmp.name
        try:
            with open(full_path, 'rb') as f_in:
                encryption_service.decrypt_stream(
                    f_in, tmp, password,
                    file_record.encryption_salt,
                    file_record.encryption_nonce,
                    file_record.encryption_metadata
                )
            tmp.close()

            activity_log_service.log_activity(g.current_user.id, 'api_decrypt_download_file', 'file', file_record.id)

            def generate():
                try:
                    with open(tmp_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

            from flask import Response
            from werkzeug.utils import secure_filename
            response = Response(
                generate(),
                mimetype=file_record.mime_type,
                headers={
                    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
            response.headers.set(
                'Content-Disposition', 'attachment',
                filename=file_record.original_filename
            )
            return response

        except Exception as e:
            if not tmp.closed:
                tmp.close()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return api_response(error="Decryption failed. Incorrect password?", code="decryption_failed", status=401)

    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/files/<file_uuid>/preview")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_preview_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)

        if file_record.is_quarantined:
            return api_response(error="File is quarantined", status=403)

        if not preview_service.is_previewable(file_record):
            return api_response(error="File not previewable", status=400)

        # Defense-in-depth: Path traversal check
        if not storage_service.is_safe_path(file_record.storage_path):
            return api_response(error="Permission denied", status=403)

        full_path = storage_service.get_full_path(file_record.storage_path)

        if not os.path.exists(full_path):
            return api_response(error="File data missing", status=404)

        response = send_file(full_path, mimetype=file_record.mime_type)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self';"
        return response
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/files/<file_uuid>/thumbnail")
@api_required
@limiter.limit("1000 per hour")
def api_get_thumbnail(file_uuid):
    size = request.args.get("size", "small")
    if size not in ['small', 'medium', 'large']:
        return api_response(error="Invalid size", status=400)

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)

        if file_record.is_quarantined:
            return api_response(error="File is quarantined", status=403)

        metadata = file_record.preview_metadata or {}
        thumbnails = metadata.get('thumbnails', {})

        # Fallback logic for sizes
        rel_thumb_path = thumbnails.get(size)
        if not rel_thumb_path:
            if size == 'medium':
                rel_thumb_path = thumbnails.get('large') or thumbnails.get('small')
            elif size == 'large':
                rel_thumb_path = thumbnails.get('medium') or thumbnails.get('small')
            elif size == 'small':
                rel_thumb_path = thumbnails.get('medium') or thumbnails.get('large')

        if rel_thumb_path:
            # Defense-in-depth: Path traversal check
            if not storage_service.is_safe_path(rel_thumb_path):
                return api_response(error="Permission denied", status=403)

            full_thumb_path = storage_service.get_full_path(rel_thumb_path)

            if os.path.exists(full_thumb_path):
                response = send_file(full_thumb_path, mimetype='image/webp', max_age=31536000)
                response.headers['X-Content-Type-Options'] = 'nosniff'
                return response

        # If we reached here, no thumbnail exists yet.
        # Trigger background generation if it's a non-encrypted image/pdf/video and not already pending.
        metadata = dict(file_record.preview_metadata or {})
        status = metadata.get('thumbnail_status', 'none')

        if status != 'pending' and not file_record.is_encrypted:
            from app.services.background_jobs import process_thumbnail_job
            from app.extensions import executor
            executor.submit(process_thumbnail_job, file_record.id, current_app._get_current_object())
            # Mark as pending to avoid multiple triggers
            metadata['thumbnail_status'] = 'pending'
            file_record.preview_metadata = metadata
            db.session.commit()

        return api_response(error="Thumbnail not found or still processing", status=404)
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/files/<file_uuid>", methods=["PATCH"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def rename_file(file_uuid):
    data = request.get_json()
    new_name = data.get("name")

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='rename')
        if not file_record:
            return api_response(error="File not found", status=404)

        file_service.rename_file(g.current_user, file_record, new_name)
        return api_response(data={
            "uuid": file_record.uuid,
            "name": file_record.original_filename,
            "type": "file",
            "mime_type": file_record.mime_type,
            "size": file_record.size_bytes,
            "is_starred": file_record.is_starred,
            "updated_at": file_record.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        })
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/files/<file_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def delete_file(file_uuid):
    permanent = request.args.get("permanent", "false").lower() == "true"
    try:
        file_service.delete_file(g.current_user, file_uuid, permanent=permanent)
        message = "File permanently deleted" if permanent else "File deleted successfully"
        return api_response(data={"message": message})
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        return api_response(error=str(e), status=status)

# --- Sharing & Public Links ---

@api_v1.route("/share", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_share_resource():
    data = request.get_json()
    res_type = data.get("resource_type")
    res_uuid = data.get("resource_uuid")
    username = data.get("username")
    permission = data.get("permission")

    try:
        resource = None
        if res_type == 'folder':
            resource = folder_service.get_folder_by_uuid(res_uuid, user=g.current_user, action='share')
        else:
            resource = file_service.get_file_by_uuid(res_uuid, user=g.current_user, action='share')

        if not resource:
            return api_response(error="Resource not found", status=404)

        share = sharing_service.share_resource(g.current_user, resource, username, permission)
        return api_response(data={"uuid": share.uuid, "username": username, "permission": permission}, status=201)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/shares", methods=["GET"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_list_shares():
    res_type = request.args.get("resource_type")
    res_uuid = request.args.get("resource_uuid")

    if not res_type or not res_uuid:
        return api_response(error="resource_type and resource_uuid required", status=400)

    try:
        resource = None
        if res_type == 'folder':
            resource = folder_service.get_folder_by_uuid(res_uuid, user=g.current_user, action='view')
        else:
            resource = file_service.get_file_by_uuid(res_uuid, user=g.current_user, action='view')

        if not resource:
            return api_response(error="Resource not found", status=404)

        shares = sharing_service.list_resource_shares(g.current_user, resource)
        return api_response(data=shares)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/share/<share_uuid>", methods=["PATCH"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_update_share(share_uuid):
    data = request.get_json()
    permission = data.get("permission")

    try:
        share = sharing_service.update_share_permission(g.current_user, share_uuid, permission)
        return api_response(data={"uuid": share.uuid, "permission": share.permission})
    except ValueError as e:
        return api_response(error=str(e), status=404)
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except Exception as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/shared-with-me")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_shared_with_me():
    shared_items = sharing_service.list_shared_with_user(g.current_user)
    serializable = []
    for item in shared_items:
        serializable.append({
            "uuid": item['resource'].uuid, # Item UUID
            "share_uuid": item['share_uuid'],
            "resource_uuid": item['resource'].uuid,
            "resource_name": item['resource'].name if hasattr(item['resource'], 'name') else item['resource'].original_filename,
            "resource_type": item['resource_type'],
            "permission": item['permission'],
            "shared_by": item['shared_by']
        })
    return api_response(data=serializable)

@api_v1.route("/share/<share_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_delete_share(share_uuid):
    try:
        sharing_service.remove_share(g.current_user, share_uuid)
        return api_response(data={"message": "Share removed"})
    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/public-links", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_create_public_link():
    data = request.get_json()
    res_type = data.get("resource_type")
    res_uuid = data.get("resource_uuid")
    password = data.get("password")
    one_time_use = data.get("one_time_use", False)
    expires_in_days = data.get("expires_in_days")
    max_downloads = data.get("max_downloads")
    link_type = data.get("link_type", "download")
    max_files = data.get("max_files", 25)
    max_upload_size_mb = data.get("max_upload_size_mb", 100)

    try:
        resource = None
        if res_type == 'folder':
            resource = folder_service.get_folder_by_uuid(res_uuid, user=g.current_user, action='share')
        else:
            resource = file_service.get_file_by_uuid(res_uuid, user=g.current_user, action='share')

        if not resource:
            return api_response(error="Resource not found", status=404)

        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=int(expires_in_days))).replace(tzinfo=None)

        raw_token, link = public_link_service.create_public_link(
            g.current_user, resource,
            password=password,
            one_time_password=one_time_use,
            expires_at=expires_at,
            max_downloads=int(max_downloads) if max_downloads else None,
            link_type=link_type,
            max_files=int(max_files),
            max_upload_size_mb=int(max_upload_size_mb)
        )
        return api_response(data={"token": raw_token, "uuid": link.uuid}, status=201)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/public-links")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_list_public_links():
    links = g.current_user.public_links
    serializable = []
    for l in links:
        if l.is_active:
            resource = None
            if l.resource_type == 'folder':
                resource = db.session.get(Folder, l.resource_id)
            else:
                resource = db.session.get(File, l.resource_id)

            serializable.append({
                "uuid": l.uuid,
                "resource_type": l.resource_type,
                "resource_uuid": resource.uuid if resource else None,
                "download_count": l.download_count,
                "is_active": l.is_active
            })
    return api_response(data=serializable)

@api_v1.route("/public-links/<link_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_delete_public_link(link_uuid):
    try:
        # Only the creator or admin can delete
        link = public_link_service.get_link_by_uuid(link_uuid, user=g.current_user)
        if not link:
            return api_response(error="Link not found", status=404)

        db.session.delete(link)
        db.session.commit()
        return api_response(data={"message": "Link deleted"})
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/files/<file_uuid>/office-preview")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_get_office_preview(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)

        if file_record.is_quarantined:
            return api_response(error="File is quarantined", status=403)

        metadata = file_record.preview_metadata or {}
        if metadata.get('office_preview_status') != 'ready':
            return api_response(error="Preview not ready", status=404)

        rel_path = metadata.get('office_preview_path')
        if not rel_path:
            return api_response(error="Preview path missing", status=404)

        # Defense-in-depth: Path traversal check
        if not storage_service.is_safe_path(rel_path):
            return api_response(error="Permission denied", status=403)

        full_path = storage_service.get_full_path(rel_path)

        if not os.path.exists(full_path):
            return api_response(error="Preview file missing", status=404)

        response = send_file(full_path, mimetype='application/pdf')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'self';"
        return response
    except PermissionError as e:
        return api_response(error=str(e), status=403)

# --- Device Management ---

@api_v1.route("/devices")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def list_devices():
    # Find unique devices with active tokens
    tokens = ApiToken.query.filter_by(user_id=g.current_user.id, revoked_at=None).all()

    # We'll use the UUID of the latest refresh token as a handle for the "session"
    devices = {}
    for t in tokens:
        if t.token_type != 'refresh': continue

        d_id = t.device_id or "unknown"
        if d_id not in devices:
            devices[d_id] = {
                "uuid": t.uuid,
                "device_id": t.device_id,
                "device_name": t.device_name,
                "last_used_at": t.last_used_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if t.last_used_at else None
            }
        else:
            # Update to newest refresh token's UUID and most recent usage
            t_last_used = t.last_used_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if t.last_used_at else None
            if not devices[d_id]["last_used_at"] or (t_last_used and t_last_used > devices[d_id]["last_used_at"]):
                devices[d_id]["last_used_at"] = t_last_used if t_last_used else devices[d_id]["last_used_at"]
                devices[d_id]["uuid"] = t.uuid

    return api_response(data=list(devices.values()))

@api_v1.route("/devices/<device_uuid>", methods=["DELETE"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def revoke_device(device_uuid):
    token = ApiToken.query.filter_by(uuid=device_uuid, user_id=g.current_user.id).first()
    if not token:
        return api_response(error="Device session not found", status=404)

    api_service.revoke_tokens(g.current_user, token.device_id)
    return api_response(data={"message": "Device revoked successfully"})

# --- Search Endpoints ---

@api_v1.route("/starred")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_get_starred():
    files = file_service.search_files(g.current_user, is_starred=True)
    folders = folder_service.search_folders(g.current_user, is_starred=True)

    results = []
    for f in folders:
        results.append({
            "uuid": f.uuid,
            "type": "folder",
            "name": f.name,
            "owner": f.owner.username,
            "is_starred": True,
            "updated_at": f.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        })
    for f in files:
        metadata = f.preview_metadata or {}
        item = {
            "uuid": f.uuid,
            "type": "file",
            "name": f.original_filename,
            "mime_type": f.mime_type,
            "size": f.size_bytes,
            "owner": f.owner.username,
            "is_starred": True,
            "updated_at": f.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            "thumbnail_status": metadata.get('thumbnail_status', 'none')
        }
        if item["thumbnail_status"] == 'ready':
            item["thumbnail_small_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='small', _external=True)
            item["thumbnail_medium_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='medium', _external=True)
            item["thumbnail_large_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='large', _external=True)
        results.append(item)
    return api_response(data=results)

@api_v1.route("/recent")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_get_recent():
    files = file_service.get_recent_files(g.current_user)

    results = []
    for f in files:
        metadata = f.preview_metadata or {}
        item = {
            "uuid": f.uuid,
            "type": "file",
            "name": f.original_filename,
            "mime_type": f.mime_type,
            "size": f.size_bytes,
            "owner": f.owner.username,
            "is_starred": f.is_starred,
            "updated_at": f.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            "thumbnail_status": metadata.get('thumbnail_status', 'none')
        }
        if item["thumbnail_status"] == 'ready':
            item["thumbnail_small_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='small', _external=True)
            item["thumbnail_medium_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='medium', _external=True)
            item["thumbnail_large_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='large', _external=True)
        results.append(item)
    return api_response(data=results)

@api_v1.route("/folders/<folder_uuid>/star", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_toggle_star_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=g.current_user, action='view')
        if not folder:
            return api_response(error="Folder not found", status=404)
        new_status = folder_service.toggle_star(g.current_user, folder)
        return api_response(data={"is_starred": new_status})
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/files/<file_uuid>/star", methods=["POST"])
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_toggle_star_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='view')
        if not file_record:
            return api_response(error="File not found", status=404)
        new_status = file_service.toggle_star(g.current_user, file_record)
        return api_response(data={"is_starred": new_status})
    except PermissionError as e:
        return api_response(error=str(e), status=403)

@api_v1.route("/search")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_search():
    query = request.args.get("q")
    mime_type = request.args.get("type")
    owner_username = request.args.get("owner")
    is_starred = request.args.get("starred")
    if is_starred:
        is_starred = is_starred.lower() == "true"
    else:
        is_starred = None

    date_from_str = request.args.get("from")
    date_to_str = request.args.get("to")

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.fromisoformat(date_from_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = datetime.fromisoformat(date_to_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            pass

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Validation
    if page < 1: page = 1
    max_per_page = current_app.config.get('SEARCH_MAX_PER_PAGE', 100)
    if per_page < 1: per_page = 20
    if per_page > max_per_page: per_page = max_per_page

    # Fetch all for combined ranking and pagination
    all_files = file_service.search_files(g.current_user, query, mime_type, owner_username, is_starred, date_from, date_to)
    
    # If mime_type is specified and it's not 'folder', we should probably skip folders
    if mime_type and 'folder' not in mime_type.lower():
        all_folders = []
    else:
        all_folders = folder_service.search_folders(g.current_user, query, owner_username, is_starred, date_from, date_to)

    combined = []
    for f in all_folders:
        combined.append({
            "uuid": f.uuid,
            "type": "folder",
            "name": f.name,
            "owner": f.owner.username,
            "is_starred": f.is_starred,
            "updated_at": f.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        })
    for f in all_files:
        metadata = f.preview_metadata or {}
        item = {
            "uuid": f.uuid,
            "type": "file",
            "name": f.original_filename,
            "mime_type": f.mime_type,
            "size": f.size_bytes,
            "owner": f.owner.username,
            "is_starred": f.is_starred,
            "updated_at": f.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            "thumbnail_status": metadata.get('thumbnail_status', 'none')
        }

        item["previewable"] = preview_service.is_previewable(f)
        item["preview_type"] = preview_service.get_preview_type(f)
        item["thumbnail_status"] = metadata.get('thumbnail_status', 'none')
        if item["thumbnail_status"] == 'ready':
            item["thumbnail_small_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='small', _external=True)
            item["thumbnail_large_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='large', _external=True)
            item["thumbnail_medium_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=f.uuid, size='medium', _external=True)

        combined.append(item)

    # Ranking: Filename matches above content matches
    if query:
        q_lower = query.lower()
        def rank_key(item):
            if q_lower in item['name'].lower():
                return 0
            return 1
        combined.sort(key=rank_key)

    total = len(combined)
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    start = (page - 1) * per_page
    end = start + per_page
    paginated_results = combined[start:end]

    return api_response(data={
        "items": paginated_results,
        "pagination": {
            "total": total,
            "pages": pages,
            "current_page": page,
            "per_page": per_page,
            "has_next": page < pages,
            "has_prev": page > 1
        }
    })

# --- Sync Endpoints ---

@api_v1.route("/sync/changes")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def get_sync_changes():
    since = request.args.get("since")
    cursor = request.args.get("cursor")
    per_page = request.args.get("per_page", 100, type=int)

    changes = sync_service.get_changes(g.current_user, since_timestamp=since, cursor=cursor, per_page=per_page)
    return api_response(data=changes)

# --- ZIP Extraction Endpoints ---

@api_v1.route("/files/<file_uuid>/extract-zip", methods=["POST"])
@api_required
@limiter.limit("10 per hour")
def api_extract_zip(file_uuid):
    data = request.get_json() or {}
    dest_uuid = data.get("destination_folder_uuid")
    extract_into_named_folder = data.get("extract_into_named_folder", True)

    try:
        zip_file = file_service.get_file_by_uuid(file_uuid, user=g.current_user, action='download')
        if not zip_file:
            return api_response(error="ZIP file not found", status=404)

        if zip_file.extension != 'zip' and zip_file.mime_type != 'application/zip':
            return api_response(error="File is not a ZIP archive", status=400)

        if zip_file.is_encrypted:
            return api_response(error="Cannot extract an encrypted ZIP file.", status=400)

        if zip_file.is_quarantined:
            return api_response(error="Cannot extract a quarantined ZIP file.", status=403)

        dest_folder = None
        if dest_uuid:
            dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=g.current_user, action='upload')
            if not dest_folder:
                return api_response(error="Destination folder not found", status=404)
        else:
            dest_folder = folder_service.get_user_root_folder(g.current_user)

        if extract_into_named_folder:
            base_name = zip_file.original_filename
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]

            folder_name = folder_service.get_unique_folder_name(g.current_user, dest_folder, base_name)
            dest_folder = folder_service.create_folder(g.current_user, dest_folder, folder_name)

        # Create job
        job = ZipExtractJob(
            user_id=g.current_user.id,
            zip_file_id=zip_file.id,
            destination_folder_id=dest_folder.id if dest_folder else None,
            status='queued'
        )
        db.session.add(job)
        db.session.commit()

        # Submit background job
        from app.extensions import executor
        executor.submit(zip_extract_service.extract_zip_background, job.uuid)

        activity_log_service.log_activity(g.current_user.id, 'zip_extract_started', 'file', zip_file.id, metadata={'job_uuid': job.uuid})

        return api_response(data={
            "job_uuid": job.uuid,
            "status": job.status
        }, status=202)

    except PermissionError as e:
        return api_response(error=str(e), status=403)
    except ValueError as e:
        return api_response(error=str(e), status=400)

@api_v1.route("/zip-extractions/<job_uuid>")
@api_required
@limiter.limit(lambda: current_app.config.get("API_RATE_LIMIT", "100 per minute"), on_breach=lambda limit: api_response(error="Too many requests", code="rate_limit_exceeded", status=429)[0])
def api_get_zip_extraction_status(job_uuid):
    job = ZipExtractJob.query.filter_by(uuid=job_uuid, user_id=g.current_user.id).first()
    if not job:
        return api_response(error="Job not found", status=404)

    return api_response(data={
        "uuid": job.uuid,
        "status": job.status,
        "summary": job.summary_json,
        "error_message": job.error_message,
        "created_at": job.created_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if job.created_at else None,
        "started_at": job.started_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if job.started_at else None,
        "completed_at": job.completed_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if job.completed_at else None
    })
