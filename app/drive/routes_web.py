"""
Description: Provides drive-related web route handlers for file and folder operations.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import tempfile
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, current_app, Response
from flask_login import login_required, current_user
from app.extensions import limiter, db
from app.services.folder_service import folder_service
from app.services.file_service import file_service
from app.services.upload_service import upload_service
from app.services.storage_service import storage_service
from app.services.activity_log_service import activity_log_service
from app.services.preview_service import preview_service
from app.services.antivirus_service import antivirus_service
from app.services.encryption_service import encryption_service
from app.services.password_service import password_service
from app.api.services import api_service
from app.sharing.services import sharing_service
from app.drive.permissions import can_access, can_upload_to_folder, can_delete
from app.models.file import File
from app.models.folder import Folder
from app.models.zip_extract_job import ZipExtractJob
from app.services.zip_extract_service import zip_extract_service

drive_web = Blueprint("drive", __name__)

@drive_web.route("/")
@drive_web.route("/dashboard")
@drive_web.route("/my-drive")
@login_required
def dashboard():
    root_folder = folder_service.get_user_root_folder(current_user)
    if not root_folder:
        # Fallback if root folder doesn't exist for some reason
        root_folder = folder_service.create_root_folder_for_user(current_user)
        db.session.commit()

    return redirect(url_for("drive.view_folder", folder_uuid=root_folder.uuid))

@drive_web.route("/folders/<folder_uuid>")
@login_required
def view_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='view')
        if not folder:
            abort(404)
    except PermissionError:
        abort(403)

    # Sorting
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', current_app.config.get('DRIVE_PAGE_SIZE', 50), type=int)

    result = folder_service.list_folder_contents_paginated(
        current_user, folder, page=page, per_page=per_page, sort_by=sort_by, order=order, iso_dates=False
    )

    path = folder_service.get_path(folder)

    # For the move modal
    all_folders = Folder.query.filter_by(owner_id=current_user.id, is_deleted=False).order_by(Folder.name).all()

    return render_template(
        "drive/dashboard.html",
        title=folder.name,
        current_folder=folder,
        items=result["items"],
        pagination=result["pagination"],
        path=path,
        sort_by=sort_by,
        order=order,
        current_user_folders=all_folders
    )

@drive_web.route("/folders/create", methods=["POST"])
@login_required
def create_folder():
    name = request.form.get("name")
    parent_uuid = request.form.get("parent_uuid")

    if not name:
        flash("Folder name is required.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    try:
        parent_folder = None
        if parent_uuid:
            parent_folder = folder_service.get_folder_by_uuid(parent_uuid, user=current_user, action='upload')
            if not parent_folder:
                abort(404)
        else:
            # If no parent_uuid, use user's root folder
            parent_folder = folder_service.get_user_root_folder(current_user)

        folder_service.create_folder(current_user, parent_folder, name)
        flash(f"Folder '{name}' created successfully.", "success")
        return redirect(url_for("drive.view_folder", folder_uuid=parent_folder.uuid))
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))
    except Exception as e:
        flash("An error occurred while creating the folder.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/folders/<folder_uuid>/rename", methods=["POST"])
@login_required
def rename_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='rename')
        if not folder:
            abort(404)

        if folder.is_root:
            flash("Root folder cannot be renamed.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        new_name = request.form.get("name")
        if not new_name:
            flash("Folder name is required.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        folder_service.rename_folder(current_user, folder, new_name)
        flash(f"Folder renamed to '{new_name}' successfully.", "success")
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred while renaming the folder.", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/folders/<folder_uuid>/policy", methods=["POST"])
@login_required
def update_folder_policy(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='edit') # Using edit permission
        if not folder:
            abort(404)

        encrypt_new_uploads = request.form.get("encrypt_new_uploads") == "true"
        folder.encrypt_new_uploads = encrypt_new_uploads
        db.session.commit()

        flash(f"Settings updated for '{folder.name}'.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error updating settings: {str(e)}", "danger")

    return redirect(url_for("drive.view_folder", folder_uuid=folder_uuid))

@drive_web.route("/folders/<folder_uuid>/delete", methods=["POST"])
@login_required
def delete_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='delete')
        if not folder:
            abort(404)

        if folder.is_root:
            flash("Root folder cannot be deleted.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        parent_uuid = folder.parent.uuid if folder.parent else None

        folder_service.soft_delete_folder(current_user, folder)
        flash(f"Folder '{folder.name}' deleted successfully.", "success")

        if parent_uuid:
            return redirect(url_for("drive.view_folder", folder_uuid=parent_uuid))
        return redirect(url_for("drive.dashboard"))
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))
    except Exception as e:
        flash("An error occurred while deleting the folder.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/files/<file_uuid>/download")
@login_required
def download_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='download')
        if not file_record:
            abort(404)

        if file_record.is_encrypted:
            return redirect(url_for('drive.decrypt_file', file_uuid=file_uuid))

        if file_record.scan_status == 'infected':
            flash("Download blocked: Malware detected in this file.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        if not file_record.is_encrypted and antivirus_service.is_strict_mode() and file_record.scan_status in ['pending', 'scan_failed']:
            flash("Download blocked: File scan is pending or failed. Strict antivirus policy is active.", "warning")
            return redirect(request.referrer or url_for("drive.dashboard"))
    except PermissionError:
        abort(403)

    activity_log_service.log_activity(current_user.id, 'download_file', 'file', file_record.id)

    full_path = storage_service.get_full_path(file_record.storage_path)
    if not os.path.exists(full_path):
        flash("The physical file is missing from storage.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    # Security: Ensure path traversal protection
    if not storage_service.is_safe_path(file_record.storage_path):
        abort(403)

    return send_file(
        full_path,
        as_attachment=True,
        download_name=file_record.original_filename,
        mimetype=file_record.mime_type
    )

@drive_web.route("/files/<file_uuid>/decrypt", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config.get("DECRYPT_RATE_LIMIT", "5 per minute"))
def decrypt_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='download')
        if not file_record:
            abort(404)

        if not file_record.is_encrypted:
            return redirect(url_for('drive.download_file', file_uuid=file_uuid))

        # Security: Ensure path traversal protection
        if not storage_service.is_safe_path(file_record.storage_path):
            abort(403)

    except PermissionError:
        abort(403)

    if request.method == "POST":
        # Rate limit decryption attempts
        # Since we are using current_app.config['DECRYPT_RATE_LIMIT'], we use g.limiter or the decorator if possible
        # However, decorators are evaluated at import time.
        # For dynamic limits we might need a workaround or just hope limiter handles it.
        # Standard approach in this app seems to be @limiter.limit() with string.

        password = request.form.get("password")
        if not password:
            flash("Password is required.", "danger")
            return render_template("drive/decrypt.html", file=file_record)

        # Decrypt to temp file
        full_path = storage_service.get_full_path(file_record.storage_path)
        if not os.path.exists(full_path):
            flash("Physical file not found.", "danger")
            return redirect(url_for('drive.dashboard'))

        # Decrypt to a temporary file first to verify the password (GCM tag)
        # before sending it to the user.
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

            activity_log_service.log_activity(current_user.id, 'decrypt_download_file', 'file', file_record.id)

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
            flash("Decryption failed. Incorrect password?", "danger")
            return render_template("drive/decrypt.html", file=file_record)

    return render_template("drive/decrypt.html", file=file_record)

@drive_web.route("/bulk/delete", methods=["POST"])
@login_required
def bulk_delete():
    folder_uuids = request.form.getlist("folder_uuids[]")
    file_uuids = request.form.getlist("file_uuids[]")

    deleted_count = 0
    errors = []

    for f_uuid in folder_uuids:
        try:
            folder = folder_service.get_folder_by_uuid(f_uuid, user=current_user, action='delete')
            if folder and not folder.is_root:
                folder_service.soft_delete_folder(current_user, folder)
                deleted_count += 1
        except Exception as e:
            errors.append(f"Folder {f_uuid}: {str(e)}")

    for f_uuid in file_uuids:
        try:
            file_rec = file_service.get_file_by_uuid(f_uuid, user=current_user, action='delete')
            if file_rec:
                file_service.soft_delete_file(current_user, file_rec)
                deleted_count += 1
        except Exception as e:
            errors.append(f"File {f_uuid}: {str(e)}")

    if deleted_count > 0:
        flash(f"Successfully deleted {deleted_count} items.", "success")
    if errors:
        flash(f"Errors occurred: {', '.join(errors[:3])}", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/bulk/move", methods=["POST"])
@login_required
def bulk_move():
    folder_uuids = request.form.getlist("folder_uuids[]")
    file_uuids = request.form.getlist("file_uuids[]")
    dest_uuid = request.form.get("destination_uuid")

    if not dest_uuid:
        flash("Destination folder is required.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    try:
        dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=current_user, action='upload')
        if not dest_folder:
            abort(404)
    except PermissionError:
        abort(403)

    moved_count = 0
    errors = []

    for f_uuid in folder_uuids:
        try:
            folder = folder_service.get_folder_by_uuid(f_uuid, user=current_user, action='move')
            if folder:
                folder_service.move_folder(current_user, folder, dest_folder)
                moved_count += 1
        except Exception as e:
            errors.append(f"Folder {f_uuid}: {str(e)}")

    for f_uuid in file_uuids:
        try:
            file_rec = file_service.get_file_by_uuid(f_uuid, user=current_user, action='move')
            if file_rec:
                file_service.move_file(current_user, file_rec, dest_folder)
                moved_count += 1
        except Exception as e:
            errors.append(f"File {f_uuid}: {str(e)}")

    if moved_count > 0:
        flash(f"Successfully moved {moved_count} items.", "success")
    if errors:
        flash(f"Errors occurred: {', '.join(errors[:3])}", "danger")

    return redirect(url_for("drive.view_folder", folder_uuid=dest_folder.uuid))

@drive_web.route("/bulk/download")
@login_required
def bulk_download():
    # Use sets to avoid duplicates if same UUID is sent multiple times (e.g. from both list and grid views)
    folder_uuids = set(request.args.getlist("folder_uuids[]"))
    file_uuids = set(request.args.getlist("file_uuids[]"))

    files = []
    folders = []

    for f_uuid in folder_uuids:
        f = folder_service.get_folder_by_uuid(f_uuid, user=current_user, action='view')
        if f: folders.append(f)

    for f_uuid in file_uuids:
        try:
            f = file_service.get_file_by_uuid(f_uuid, user=current_user, action='download')
            if f: files.append(f)
        except PermissionError:
            # File might be quarantined or access denied, skipped during gathering
            pass

    if not files and not folders:
        flash("No valid items selected for download.", "warning")
        return redirect(request.referrer or url_for("drive.dashboard"))

    from app.services.zip_service import zip_service

    # Recursive size check
    stats = zip_service.get_recursive_items_stats(current_user, files, folders)
    total_size = stats['total_size']
    total_count = stats['total_files']

    limit_mb = current_app.config.get('ZIP_EXPORT_MAX_MB', 250)
    if total_size > limit_mb * 1024 * 1024:
        flash(f"Total download size exceeds {limit_mb}MB limit for ZIP creation. Selected size: {total_size // (1024*1024)}MB", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    # UI Feedback for skipped files
    skipped_msgs = []
    if stats['skipped_encrypted'] > 0:
        skipped_msgs.append(f"{stats['skipped_encrypted']} encrypted")
    if stats['skipped_quarantined'] > 0:
        skipped_msgs.append(f"{stats['skipped_quarantined']} quarantined")
    if stats['skipped_missing'] > 0:
        skipped_msgs.append(f"{stats['skipped_missing']} missing")

    if skipped_msgs:
        flash(f"ZIP created. {', '.join(skipped_msgs)} files were skipped.", "info")

    activity_log_service.log_activity(current_user.id, 'bulk_download_zip', metadata={
        'file_count': total_count,
        'size_bytes': total_size,
        'skipped': stats
    })

    zip_path = zip_service.create_zip_file(current_user, files, folders)

    def generate():
        try:
            with open(zip_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    response = Response(
        generate(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f"attachment; filename=drive_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            'Cache-Control': 'no-store',
            'X-Drive-Zip-Skipped': f"encrypted={stats['skipped_encrypted']};quarantined={stats['skipped_quarantined']};missing={stats['skipped_missing']}"
        }
    )
    return response

@drive_web.route("/files/<file_uuid>/rename", methods=["POST"])
@login_required
def rename_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='rename')
        if not file_record:
            abort(404)

        new_name = request.form.get("name")
        if not new_name:
            flash("File name is required.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        file_service.rename_file(current_user, file_record, new_name)
        flash(f"File renamed to '{new_name}' successfully.", "success")
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred while renaming the file.", "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/files/<file_uuid>/delete", methods=["POST"])
@login_required
def delete_file(file_uuid):
    file_record = None
    dest_uuid = None
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='delete')
        if not file_record:
            abort(404)

        # Better redirect: if we know the folder, capture it before deletion
        dest_uuid = file_record.folder.uuid if file_record.folder else None

        file_service.soft_delete_file(current_user, file_record)
        flash(f"File '{file_record.original_filename}' deleted successfully.", "success")
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash("An error occurred while deleting the file.", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    if dest_uuid:
        return redirect(url_for("drive.view_folder", folder_uuid=dest_uuid))

    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/files/<file_uuid>/copy", methods=["POST"])
@login_required
def copy_file(file_uuid):
    dest_uuid = request.form.get("destination_uuid")

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)

        dest_folder = None
        if dest_uuid:
            dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=current_user, action='upload')
            if not dest_folder:
                abort(404)
        else:
            dest_folder = folder_service.get_user_root_folder(current_user)

        file_service.copy_file(current_user, file_record, dest_folder)
        flash(f"File '{file_record.original_filename}' copied to your drive.", "success")
        return redirect(url_for('drive.view_folder', folder_uuid=dest_folder.uuid))
    except PermissionError:
        abort(403)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for('drive.dashboard'))

@drive_web.route("/upload", methods=["POST"])
@login_required
def upload_file():
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash("No selected files", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

    folder_uuid = request.form.get("folder_uuid")
    prefix = request.form.get("prefix")
    relative_paths = request.form.getlist("relative_paths[]")
    is_encrypted = request.form.get("is_encrypted") == "true"
    password = request.form.get("password")

    try:
        folder = None
        if folder_uuid:
            folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='upload')
            if not folder:
                abort(404)
        else:
            folder = folder_service.get_user_root_folder(current_user)

        if len(files) == 1 and not prefix and not relative_paths:
            # Single file upload (original behavior)
            custom_name = request.form.get("custom_name")
            upload_service.process_upload(
                current_user, folder, files[0],
                filename=custom_name,
                is_encrypted=is_encrypted,
                password=password
            )
            db.session.commit()
            flash(f"File '{files[0].filename}' uploaded successfully.", "success")
        else:
            # Bulk or directory upload
            uploaded, errors = upload_service.process_bulk_upload(
                current_user, folder, files,
                prefix=prefix,
                relative_paths=relative_paths,
                is_encrypted=is_encrypted,
                password=password
            )

            if uploaded:
                flash(f"Successfully uploaded {len(uploaded)} files.", "success")
            if errors:
                for error in errors[:5]: # Show first 5 errors
                    flash(error, "danger")
                if len(errors) > 5:
                    flash(f"...and {len(errors) - 5} more errors.", "danger")

        return redirect(url_for("drive.view_folder", folder_uuid=folder.uuid))
    except PermissionError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return {"success": False, "error": "Permission denied"}, 403
        abort(403)
    except ValueError as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return {"success": False, "error": str(e)}, 400
        flash(str(e), "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return {"success": False, "error": str(e)}, 500
        flash(f"An error occurred during upload: {str(e)}", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))


@drive_web.route("/starred")
@login_required
def starred():
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    per_page = 20

    all_files = file_service.search_files(current_user, is_starred=True)
    all_folders = folder_service.search_folders(current_user, is_starred=True)

    total = len(all_files) + len(all_folders)
    pages = (total + per_page - 1) // per_page

    combined = []
    for f in all_folders:
        combined.append({'obj': f, 'type': 'folder'})
    for f in all_files:
        combined.append({'obj': f, 'type': 'file'})

    # For Starred items, we might want to sort by updated_at or name
    combined.sort(key=lambda x: (x['obj'].updated_at), reverse=True)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = combined[start:end]

    pagination = {
        'total': total,
        'pages': pages,
        'current_page': page,
        'per_page': per_page,
        'has_next': page < pages,
        'has_prev': page > 1
    }

    return render_template(
        "drive/search_results.html",
        title="Starred",
        query="Starred items",
        items=paginated_items,
        pagination=pagination,
        endpoint="drive.starred"
    )

@drive_web.route("/recent")
@login_required
def recent():
    files = File.query.filter_by(owner_id=current_user.id, is_deleted=False).order_by(File.updated_at.desc()).limit(50).all()
    return render_template("drive/search_results.html", title="Recent", query="Recently modified files", files=files, folders=[])

@drive_web.route("/folders/<folder_uuid>/star", methods=["POST"])
@login_required
def toggle_star_folder(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='view')
        if not folder:
            abort(404)
        folder_service.toggle_star(current_user, folder)
    except PermissionError:
        abort(403)
    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/files/<file_uuid>/star", methods=["POST"])
@login_required
def toggle_star_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)
        file_service.toggle_star(current_user, file_record)
    except PermissionError:
        abort(403)
    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/storage-usage")
@login_required
def storage_usage():
    stats = file_service.get_user_storage_stats(current_user)
    return render_template("drive/storage.html", title="Storage Usage", stats=stats)

@drive_web.route("/search")
@login_required
def search():
    query = request.args.get("q")
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    per_page = 20

    if not query:
        return redirect(url_for("drive.dashboard"))

    # Need total count for metadata
    all_files = file_service.search_files(current_user, query=query)
    all_folders = folder_service.search_folders(current_user, query=query)

    total = len(all_files) + len(all_folders)
    pages = (total + per_page - 1) // per_page

    # Combined results for pagination
    # Combine results and sort before slicing
    combined = []
    for f in all_folders:
        combined.append({'obj': f, 'type': 'folder'})
    for f in all_files:
        combined.append({'obj': f, 'type': 'file'})

    # Re-apply ranking to combined list
    if query:
        q_lower = query.lower()
        def rank_key(item):
            name = item['obj'].name if item['type'] == 'folder' else item['obj'].original_filename
            if q_lower in name.lower():
                return 0
            return 1
        combined.sort(key=rank_key)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = combined[start:end]

    pagination = {
        'total': total,
        'pages': pages,
        'current_page': page,
        'per_page': per_page,
        'has_next': page < pages,
        'has_prev': page > 1
    }

    return render_template(
        "drive/search_results.html",
        title=f"Search results for '{query}'",
        query=query,
        items=paginated_items,
        pagination=pagination,
        endpoint="drive.search"
    )

@drive_web.route("/folders/<folder_uuid>/shares")
@login_required
def folder_shares(folder_uuid):
    try:
        folder = folder_service.get_folder_by_uuid(folder_uuid, user=current_user, action='view')
        if not folder:
            abort(404)
        shares = sharing_service.list_resource_shares(current_user, folder)
        return render_template("drive/shares.html", title=f"Shares for {folder.name}", resource=folder, resource_type='folder', shares=shares)
    except PermissionError:
        abort(403)

@drive_web.route("/files/<file_uuid>/shares")
@login_required
def file_shares(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)
        shares = sharing_service.list_resource_shares(current_user, file_record)
        return render_template("drive/shares.html", title=f"Shares for {file_record.original_filename}", resource=file_record, resource_type='file', shares=shares)
    except PermissionError:
        abort(403)

@drive_web.route("/shares/add", methods=["POST"])
@login_required
def add_share():
    res_type = request.form.get("resource_type")
    res_uuid = request.form.get("resource_uuid")
    username = request.form.get("username")
    permission = request.form.get("permission")

    try:
        resource = None
        if res_type == 'folder':
            resource = folder_service.get_folder_by_uuid(res_uuid, user=current_user, action='share')
        else:
            resource = file_service.get_file_by_uuid(res_uuid, user=current_user, action='share')

        if not resource:
            abort(404)

        sharing_service.share_resource(current_user, resource, username, permission)
        flash(f"Resource shared with {username}.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/shares/<share_uuid>/remove", methods=["POST"])
@login_required
def remove_share(share_uuid):
    try:
        sharing_service.remove_share(current_user, share_uuid)
        flash("Share removed.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/public-links")
@login_required
def public_links():
    from app.models.public_link import PublicLink
    links = PublicLink.query.filter_by(created_by_user_id=current_user.id, is_active=True).all()

    # Enrich links with resource names
    enriched_links = []
    for link in links:
        resource_name = "Unknown"
        if link.resource_type == 'folder':
            res = db.session.get(Folder, link.resource_id)
            if res: resource_name = res.name
        else:
            res = db.session.get(File, link.resource_id)
            if res: resource_name = res.original_filename

        enriched_links.append({
            'obj': link,
            'resource_name': resource_name
        })

    return render_template("drive/public_links.html", title="Public Links", links=enriched_links)

@drive_web.route("/trash")
@login_required
def trash():
    from app.models.folder import Folder
    from app.models.file import File

    # We want to show "top-level" deleted items for the user
    # Folders that are deleted but their parent is not deleted (or is root and not deleted, but root is never deleted)
    deleted_folders = Folder.query.filter(
        Folder.owner_id == current_user.id,
        Folder.is_deleted == True
    ).all()

    # Filter to only show those whose parent is NOT deleted
    top_deleted_folders = [f for f in deleted_folders if not f.parent or not f.parent.is_deleted]

    deleted_files = File.query.filter(
        File.owner_id == current_user.id,
        File.is_deleted == True
    ).all()

    top_deleted_files = [f for f in deleted_files if not f.folder or not f.folder.is_deleted]

    return render_template(
        "drive/trash.html",
        title="Trash",
        deleted_folders=top_deleted_folders,
        deleted_files=top_deleted_files
    )

@drive_web.route("/trash/empty", methods=["POST"])
@login_required
def empty_trash():
    try:
        folder_service.empty_trash(current_user)
        flash("Trash emptied successfully.", "success")
    except Exception as e:
        flash(f"Error emptying trash: {str(e)}", "danger")
    return redirect(url_for("drive.trash"))

@drive_web.route("/folders/<folder_uuid>/restore", methods=["POST"])
@login_required
def restore_folder(folder_uuid):
    try:
        # We need a way to get a deleted folder by UUID
        from app.models.folder import Folder
        folder = Folder.query.filter_by(uuid=folder_uuid, owner_id=current_user.id, is_deleted=True).first()
        if not folder:
            abort(404)

        folder_service.restore_folder(current_user, folder)
        flash(f"Folder '{folder.name}' restored successfully.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error restoring folder: {str(e)}", "danger")
    return redirect(url_for("drive.trash"))

@drive_web.route("/folders/<folder_uuid>/permanent-delete", methods=["POST"])
@login_required
def permanent_delete_folder(folder_uuid):
    try:
        from app.models.folder import Folder
        folder = Folder.query.filter_by(uuid=folder_uuid, owner_id=current_user.id, is_deleted=True).first()
        if not folder:
            abort(404)

        folder_name = folder.name
        folder_service.permanent_delete_folder(current_user, folder)
        flash(f"Folder '{folder_name}' permanently deleted.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error deleting folder: {str(e)}", "danger")
    return redirect(url_for("drive.trash"))

@drive_web.route("/files/<file_uuid>/restore", methods=["POST"])
@login_required
def restore_file(file_uuid):
    try:
        from app.models.file import File
        file_record = File.query.filter_by(uuid=file_uuid, owner_id=current_user.id, is_deleted=True).first()
        if not file_record:
            abort(404)

        file_service.restore_file(current_user, file_record)
        flash(f"File '{file_record.original_filename}' restored successfully.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error restoring file: {str(e)}", "danger")
    return redirect(url_for("drive.trash"))

@drive_web.route("/files/<file_uuid>/permanent-delete", methods=["POST"])
@login_required
def permanent_delete_file(file_uuid):
    try:
        from app.models.file import File
        file_record = File.query.filter_by(uuid=file_uuid, owner_id=current_user.id, is_deleted=True).first()
        if not file_record:
            abort(404)

        filename = file_record.original_filename
        file_service.permanent_delete_file(current_user, file_record)
        flash(f"File '{filename}' permanently deleted.", "success")
    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error deleting file: {str(e)}", "danger")
    return redirect(url_for("drive.trash"))

@drive_web.route("/files/<file_uuid>/preview")
@login_required
def preview_file(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)

        if file_record.is_quarantined:
            flash("Access denied: File is quarantined for security reasons.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        if not file_record.is_encrypted and antivirus_service.is_strict_mode() and file_record.scan_status in ['pending', 'scan_failed']:
            flash("Preview blocked: File scan is pending or failed. Strict antivirus policy is active.", "warning")
            return redirect(request.referrer or url_for("drive.dashboard"))

        preview_type = preview_service.get_preview_type(file_record)
        text_content = None
        is_truncated = False
        if preview_type in ['text', 'csv']:
            text_content = preview_service.get_safe_text_preview(file_record)
            if len(text_content) >= 100000:
                is_truncated = True

            if file_record.extension == 'json' or file_record.mime_type == 'application/json':
                try:
                    import json
                    data = json.loads(text_content)
                    text_content = json.dumps(data, indent=4)
                except Exception:
                    pass

        path = folder_service.get_path(file_record.folder) if file_record.folder else []

        response = render_template(
            "drive/preview.html",
            file=file_record,
            preview_type=preview_type,
            text_content=text_content,
            is_truncated=is_truncated,
            path=path
        )
        return response
    except PermissionError:
        abort(403)

@drive_web.route("/files/<file_uuid>/raw-preview")
@login_required
def raw_preview(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)

        if file_record.is_quarantined:
            abort(403)

        if not file_record.is_encrypted and antivirus_service.is_strict_mode() and file_record.scan_status in ['pending', 'scan_failed']:
            abort(403)

        if not preview_service.is_previewable(file_record):
            abort(400)

        # Defense-in-depth: Path traversal check
        if not storage_service.is_safe_path(file_record.storage_path):
            abort(403)

        full_path = storage_service.get_full_path(file_record.storage_path)

        if not os.path.exists(full_path):
            abort(404)

        response = send_file(
            full_path,
            as_attachment=False,
            mimetype=file_record.mime_type,
            download_name=file_record.original_filename
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Add CSP for raw preview to prevent script execution if any
        response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline';"
        return response
    except PermissionError:
        abort(403)

@drive_web.route("/files/<file_uuid>/thumbnail/<size>")
@login_required
@limiter.limit("1000 per hour")
def get_thumbnail(file_uuid, size):
    if size not in ['small', 'large']:
        abort(400)

    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)

        if file_record.is_quarantined:
            abort(403)

        if not file_record.is_encrypted and antivirus_service.is_strict_mode() and file_record.scan_status in ['pending', 'scan_failed']:
            abort(403)

        # Check if thumbnail exists in metadata
        metadata = file_record.preview_metadata or {}
        thumbnails = metadata.get('thumbnails', {})
        rel_thumb_path = thumbnails.get(size)

        if rel_thumb_path:
            # Defense-in-depth: Path traversal check
            if not storage_service.is_safe_path(rel_thumb_path):
                abort(403)

            full_thumb_path = storage_service.get_full_path(rel_thumb_path)

            if os.path.exists(full_thumb_path):
                response = send_file(full_thumb_path, mimetype='image/webp')
                response.headers['X-Content-Type-Options'] = 'nosniff'
                return response

        return abort(404)

    except PermissionError:
        abort(403)

@drive_web.route("/account/security")
@login_required
def security_settings():
    return render_template("drive/security.html", title="Security Settings")

@drive_web.route("/account/change-password", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def change_password():
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for('drive.security_settings'))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for('drive.security_settings'))

    if current_password == new_password:
        flash("New password must be different from the current password.", "danger")
        return redirect(url_for('drive.security_settings'))

    is_valid, error_msg = password_service.validate_password(new_password)
    if not is_valid:
        flash(error_msg, "danger")
        return redirect(url_for('drive.security_settings'))

    current_user.set_password(new_password)

    # Revoke all API tokens for this user for security
    api_service.revoke_tokens(current_user)

    db.session.commit()

    activity_log_service.log_activity(current_user.id, 'password_changed')
    flash("Your password has been changed successfully. All other API sessions have been logged out.", "success")
    return redirect(url_for('drive.security_settings'))

@drive_web.route("/zip-extractions")
@login_required
def list_zip_extractions():
    jobs = ZipExtractJob.query.filter_by(user_id=current_user.id).order_by(ZipExtractJob.created_at.desc()).limit(20).all()
    return render_template("drive/extraction_jobs.html", jobs=jobs)

@drive_web.route("/files/<file_uuid>/extract-zip", methods=["POST"])
@login_required
def extract_zip(file_uuid):
    extract_into_named_folder = request.form.get("extract_into_named_folder") == "true"
    dest_uuid = request.form.get("destination_uuid")

    try:
        zip_file = file_service.get_file_by_uuid(file_uuid, user=current_user, action='download')
        if not zip_file:
            abort(404)

        if zip_file.extension != 'zip' and zip_file.mime_type != 'application/zip':
            flash("File is not a ZIP archive.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        if zip_file.is_encrypted:
            flash("Cannot extract an encrypted ZIP file.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        if zip_file.is_quarantined:
            flash("Cannot extract a quarantined ZIP file.", "danger")
            return redirect(request.referrer or url_for("drive.dashboard"))

        dest_folder = None
        if dest_uuid:
            dest_folder = folder_service.get_folder_by_uuid(dest_uuid, user=current_user, action='upload')
            if not dest_folder:
                abort(404)
        else:
            dest_folder = folder_service.get_user_root_folder(current_user)

        if extract_into_named_folder:
            base_name = zip_file.original_filename
            if '.' in base_name:
                base_name = base_name.rsplit('.', 1)[0]

            folder_name = folder_service.get_unique_folder_name(current_user, dest_folder, base_name)
            dest_folder = folder_service.create_folder(current_user, dest_folder, folder_name)

        job = ZipExtractJob(
            user_id=current_user.id,
            zip_file_id=zip_file.id,
            destination_folder_id=dest_folder.id if dest_folder else None,
            status='queued'
        )
        db.session.add(job)
        db.session.commit()

        from app.extensions import executor
        executor.submit(zip_extract_service.extract_zip_background, job.uuid)

        activity_log_service.log_activity(current_user.id, 'zip_extract_started', 'file', zip_file.id, metadata={'job_uuid': job.uuid})

        flash("ZIP extraction started in the background.", "success")
        return redirect(url_for("drive.list_zip_extractions"))

    except PermissionError:
        abort(403)
    except Exception as e:
        flash(f"Error starting extraction: {str(e)}", "danger")
        return redirect(request.referrer or url_for("drive.dashboard"))

@drive_web.route("/files/<file_uuid>/office-preview.pdf")
@login_required
def get_office_preview(file_uuid):
    try:
        file_record = file_service.get_file_by_uuid(file_uuid, user=current_user, action='view')
        if not file_record:
            abort(404)

        if file_record.is_quarantined:
            abort(403)

        if not file_record.is_encrypted and antivirus_service.is_strict_mode() and file_record.scan_status in ['pending', 'scan_failed']:
            abort(403)

        metadata = file_record.preview_metadata or {}
        if metadata.get('office_preview_status') != 'ready':
            abort(404)

        rel_path = metadata.get('office_preview_path')
        if not rel_path:
            abort(404)

        # Defense-in-depth: Path traversal check
        if not storage_service.is_safe_path(rel_path):
            abort(403)

        full_path = storage_service.get_full_path(rel_path)

        if not os.path.exists(full_path):
            abort(404)

        response = send_file(full_path, mimetype='application/pdf')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Add CSP for raw preview to prevent script execution if any
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'self';"
        return response

    except PermissionError:
        abort(403)
