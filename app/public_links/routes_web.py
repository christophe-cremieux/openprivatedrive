"""
Description: Handles public link web routes and public upload interactions.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file
from flask_login import login_required, current_user
from app.public_links.services import public_link_service
from app.services.activity_log_service import activity_log_service
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.storage_service import storage_service
from app.models.file import File
from app.models.folder import Folder
from app.extensions import db, limiter
from app.config import Config
from datetime import datetime, timedelta, timezone

public_links_web = Blueprint("public_links", __name__)

@public_links_web.route("/public/create", methods=["POST"])
@login_required
def create_link():
    resource_type = request.form.get("resource_type")
    resource_uuid = request.form.get("resource_uuid")
    password = request.form.get("password")
    one_time_password = request.form.get("one_time_password") == 'true'
    expires_in_days = request.form.get("expires_in_days")
    max_downloads = request.form.get("max_downloads")
    link_type = request.form.get("link_type", "download")
    max_files = request.form.get("max_files", Config.PUBLIC_UPLOAD_MAX_FILES)
    max_upload_size_mb = request.form.get("max_upload_size_mb", Config.PUBLIC_UPLOAD_MAX_MB)
    max_upload_size_total_mb = request.form.get("max_upload_size_total_mb")

    resource = None
    if resource_type == 'folder':
        resource = folder_service.get_folder_by_uuid(resource_uuid)
    else:
        resource = file_service.get_file_by_uuid(resource_uuid)

    if not resource:
        abort(404)

    expires_at = None
    if expires_in_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=int(expires_in_days))).replace(tzinfo=None)

    try:
        raw_token, link = public_link_service.create_public_link(
            current_user, resource,
            password=password if password else None,
            one_time_password=one_time_password,
            expires_at=expires_at,
            max_downloads=int(max_downloads) if max_downloads else None,
            link_type=link_type,
            max_files=int(max_files),
            max_upload_size_mb=int(max_upload_size_mb),
            max_upload_size_total_mb=int(max_upload_size_total_mb) if max_upload_size_total_mb else None
        )
        # In a real app, we'd show the link to the user. For now, just flash success.
        if link_type == 'upload':
            public_url = url_for("public_links.view_upload_link", token=raw_token, _external=True)
        else:
            public_url = url_for("public_links.view_link", token=raw_token, _external=True)
        flash(f"Public link created: {public_url}", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred while creating the public link.", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@public_links_web.route("/public/delete/<link_uuid>", methods=["POST"])
@login_required
def delete_link(link_uuid):
    try:
        link = public_link_service.get_link_by_uuid(link_uuid, user=current_user)
        if not link:
            abort(404)

        db.session.delete(link)
        db.session.commit()
        flash("Public link revoked.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash("Error revoking link.", "danger")

    return redirect(url_for("drive.public_links"))

@public_links_web.route("/public/l/<token>", methods=["GET", "POST"])
@limiter.limit(Config.PUBLIC_LINK_RATE_LIMIT, methods=["POST"])
def view_link(token):
    link = public_link_service.get_link_by_token(token)
    if not link:
        abort(404)

    resource = None
    if link.resource_type == 'folder':
        resource = db.session.get(Folder, link.resource_id)
    else:
        resource = db.session.get(File, link.resource_id)

    if not resource or resource.is_deleted:
        abort(404)

    if request.method == "POST":
        password = request.form.get("password")
        if public_link_service.validate_password(link, password):
            # Password valid or not required. Serve the file or show folder.
            if link.resource_type == 'file':
                public_link_service.increment_download_count(link)
                activity_log_service.log_activity(None, 'public_link_download', 'file', resource.id)
                full_path = storage_service.get_full_path(resource.storage_path)
                return send_file(
                    full_path,
                    as_attachment=True,
                    download_name=resource.original_filename,
                    mimetype=resource.mime_type
                )
            else:
                # For folders, we'd show a simplified listing. Not requested yet.
                return "Public folder view not implemented yet."
        else:
            flash("Invalid password.", "danger")

    return render_template("public_links/view.html", link=link, resource=resource, token=token)

@public_links_web.route("/public/upload/<token>", methods=["GET", "POST"])
def view_upload_link(token):
    link = public_link_service.get_link_by_token(token)
    if not link or link.link_type != 'upload':
        abort(404)

    folder = db.session.get(Folder, link.resource_id)
    if not folder or folder.is_deleted:
        abort(404)

    if request.method == "POST":
        password = request.form.get("password")
        if public_link_service.validate_password(link, password):
            # Show upload form
            return render_template("public_links/upload.html", link=link, folder=folder, token=token, authenticated=True)
        else:
            flash("Invalid password.", "danger")

    return render_template("public_links/upload.html", link=link, folder=folder, token=token, authenticated=False)

@public_links_web.route("/public/upload/<token>/process", methods=["POST"])
@limiter.limit("5 per minute")
def handle_public_upload(token):
    link = public_link_service.get_link_by_token(token)
    if not link or link.link_type != 'upload':
        abort(404)

    folder = db.session.get(Folder, link.resource_id)
    if not folder or folder.is_deleted:
        abort(404)

    # Validate password again for the upload request
    password = request.form.get("password")
    if not public_link_service.validate_password(link, password):
        abort(403)

    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash("No files provided", "danger")
        return redirect(url_for("public_links.view_upload_link", token=token))

    # Initial check
    upload_count = link.upload_count or 0
    uploaded_bytes = link.uploaded_bytes or 0

    if upload_count + len(files) > link.max_files:
        activity_log_service.log_activity(None, 'public_upload_rejected', 'folder', folder.id, metadata={
            'reason': 'max_files_exceeded',
            'link_uuid': link.uuid,
            'curr_count': upload_count,
            'requested': len(files)
        })
        flash(f"Maximum {link.max_files} files allowed for this link. You already uploaded {upload_count} files.", "danger")
        return redirect(url_for("public_links.view_upload_link", token=token))

    # Reject encryption for public uploads
    if request.form.get("is_encrypted") == "true":
        flash("Encryption is not supported for public uploads.", "danger")
        return redirect(url_for("public_links.view_upload_link", token=token))

    # Check total size
    total_size = 0
    for f in files:
        f.seek(0, 2)
        total_size += f.tell()
        f.seek(0)

    if total_size > link.max_upload_size_mb * 1024 * 1024:
        flash(f"Maximum total upload size per request is {link.max_upload_size_mb} MB.", "danger")
        return redirect(url_for("public_links.view_upload_link", token=token))

    if link.max_upload_size_total_mb:
        cumulative_limit = link.max_upload_size_total_mb * 1024 * 1024
        if uploaded_bytes + total_size > cumulative_limit:
            activity_log_service.log_activity(None, 'public_upload_rejected', 'folder', folder.id, metadata={
                'reason': 'cumulative_size_exceeded',
                'link_uuid': link.uuid,
                'curr_bytes': uploaded_bytes,
                'requested_bytes': total_size,
                'limit': cumulative_limit
            })
            remaining = max(0, cumulative_limit - uploaded_bytes)
            flash(f"Cumulative upload limit reached. Remaining: {remaining // (1024*1024)} MB", "danger")
            return redirect(url_for("public_links.view_upload_link", token=token))

    try:
        from app.models.user import User
        owner = db.session.get(User, folder.owner_id)

        public_link_service.handle_public_upload_transaction(
            link.id, files, folder, owner, request.remote_addr, total_size
        )

        db.session.commit()

        flash(f"Successfully uploaded {len(files)} files.", "success")
        return render_template("public_links/upload_success.html", folder_name=folder.name)
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for("public_links.view_upload_link", token=token))
