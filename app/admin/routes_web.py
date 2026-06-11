"""
Description: Defines admin dashboard web routes and admin page handlers.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import shutil
import subprocess
import tempfile
from functools import wraps
from flask import Blueprint, render_template, abort, current_app, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db, executor, limiter
from app.models.file import File
from app.models.system_stat import SystemStat
from app.services.activity_log_service import activity_log_service
from app.services.background_jobs import cleanup_storage_job, process_file_pipeline_job
from app.services.encryption_service import encryption_service
from app.services.password_service import password_service
from app.services.antivirus_service import antivirus_service
from app.api.services import api_service
from app.services.upload_policy_service import upload_policy_service
from app.config import Config

admin_web = Blueprint("admin", __name__, url_prefix="/admin")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@admin_web.route("/")
@login_required
@admin_required
def dashboard():
    stats = activity_log_service.get_dashboard_stats()
    recent_logs = activity_log_service.get_recent_logs(limit=10)
    return render_template("admin/dashboard.html", title="Admin - Dashboard", stats=stats, recent_logs=recent_logs)

@admin_web.route("/users")
@login_required
@admin_required
def users():
    user_stats = activity_log_service.get_all_users_with_stats()
    return render_template("admin/users.html", title="Admin - Users", user_stats=user_stats)

@admin_web.route("/users/create", methods=["POST"])
@login_required
@admin_required
def create_user():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    is_admin = request.form.get("is_admin") == "true"

    if not username or not email or not password:
        flash("All fields are required.", "danger")
        return redirect(url_for('admin.users'))

    is_valid, error_msg = password_service.validate_password(password)
    if not is_valid:
        flash(error_msg, "danger")
        return redirect(url_for('admin.users'))

    from app.auth.services import auth_service
    try:
        auth_service.create_user(username, email, password, is_admin=is_admin)
        flash(f"User {username} created successfully.", "success")
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "danger")

    return redirect(url_for('admin.users'))

@admin_web.route("/users/<user_uuid>/reset-password", methods=["POST"])
@login_required
@admin_required
def create_reset_link(user_uuid):
    from app.models.user import User
    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        abort(404)

    raw_token, expires_at = password_service.generate_reset_token(user, admin_id=current_user.id)
    reset_url = url_for('auth.reset_password', token=raw_token, _external=True)

    activity_log_service.log_activity(current_user.id, 'password_reset_link_created', metadata={'target_user_id': user.id})

    return render_template(
        "admin/reset_link_result.html",
        title="Reset Link Generated",
        reset_url=reset_url,
        target_username=user.username
    )

@admin_web.route("/users/<user_uuid>/revoke-tokens", methods=["POST"])
@login_required
@admin_required
def revoke_user_tokens(user_uuid):
    from app.models.user import User
    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        abort(404)

    api_service.revoke_tokens(user)
    activity_log_service.log_activity(current_user.id, 'admin_revoke_user_tokens', metadata={'target_user_id': user.id})
    flash(f"All API tokens for {user.username} have been revoked.", "success")
    return redirect(url_for('admin.users'))

@admin_web.route("/users/<user_uuid>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_uuid):
    from app.models.user import User
    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        abort(404)

    if user.id == current_user.id:
        flash("You cannot deactivate yourself.", "danger")
        return redirect(url_for('admin.users'))

    user.is_active = False
    api_service.revoke_tokens(user)
    db.session.commit()

    activity_log_service.log_activity(current_user.id, 'admin_deactivate_user', metadata={'target_user_id': user.id})
    flash(f"User {user.username} has been deactivated.", "success")
    return redirect(url_for('admin.users'))

@admin_web.route("/users/<user_uuid>/reactivate", methods=["POST"])
@login_required
@admin_required
def reactivate_user(user_uuid):
    from app.models.user import User
    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        abort(404)

    user.is_active = True
    db.session.commit()

    activity_log_service.log_activity(current_user.id, 'admin_reactivate_user', metadata={'target_user_id': user.id})
    flash(f"User {user.username} has been reactivated.", "success")
    return redirect(url_for('admin.users'))

@admin_web.route("/users/<user_uuid>/quota", methods=["POST"])
@login_required
@admin_required
def update_user_quota(user_uuid):
    from app.models.user import User
    user = User.query.filter_by(uuid=user_uuid).first()
    if not user:
        abort(404)

    quota_gb = request.form.get("quota_gb", type=float)
    if quota_gb is None or quota_gb < 0:
        flash("Invalid quota value.", "danger")
    else:
        user.storage_quota_bytes = int(quota_gb * 1024 * 1024 * 1024)
        db.session.commit()
        flash(f"Storage quota updated for {user.username}.", "success")

    return redirect(url_for('admin.users'))

@admin_web.route("/public-links")
@login_required
@admin_required
def public_links():
    from app.models.public_link import PublicLink
    from app.models.folder import Folder
    from sqlalchemy.orm import joinedload
    links = PublicLink.query.options(joinedload(PublicLink.created_by)).order_by(PublicLink.created_at.desc()).all()

    # Optimize N+1: batch fetch folders and files
    folder_ids = [l.resource_id for l in links if l.resource_type == 'folder']
    file_ids = [l.resource_id for l in links if l.resource_type == 'file']

    folders_map = {f.id: f.name for f in Folder.query.filter(Folder.id.in_(folder_ids)).all()} if folder_ids else {}
    files_map = {f.id: f.original_filename for f in File.query.filter(File.id.in_(file_ids)).all()} if file_ids else {}

    enriched_links = []
    for link in links:
        resource_name = "Unknown"
        if link.resource_type == 'folder':
            resource_name = folders_map.get(link.resource_id, "Unknown Folder")
        else:
            resource_name = files_map.get(link.resource_id, "Unknown File")

        enriched_links.append({
            'obj': link,
            'resource_name': resource_name
        })

    return render_template("admin/public_links.html", title="Admin - Public Links", links=enriched_links)

@admin_web.route("/public-links/<link_uuid>/revoke", methods=["POST"])
@login_required
@admin_required
def revoke_public_link(link_uuid):
    from app.models.public_link import PublicLink
    link = PublicLink.query.filter_by(uuid=link_uuid).first()
    if not link:
        abort(404)

    db.session.delete(link)
    db.session.commit()
    flash("Public link revoked.", "success")
    return redirect(url_for('admin.public_links'))

@admin_web.route("/logs")
@login_required
@admin_required
def logs():
    category = request.args.get("category")
    logs = activity_log_service.get_recent_logs(category=category)
    return render_template("admin/logs.html", title="Admin - Logs", logs=logs, current_category=category)

@admin_web.route("/storage")
@login_required
@admin_required
def storage():
    storage_stats = activity_log_service.get_system_storage_usage()
    return render_template("admin/storage.html", title="Admin - Storage", stats=storage_stats)

@admin_web.route("/upload-policy")
@login_required
@admin_required
def upload_policy():
    policy = upload_policy_service.get_policy()
    max_upload_size = SystemStat.get_stat('global_max_upload_size_mb', 0)
    antivirus_enabled = antivirus_service.is_enabled()
    antivirus_strict_mode = antivirus_service.is_strict_mode()
    return render_template(
        "admin/upload_policy.html",
        title="Admin - Upload Policy",
        policy=policy,
        max_upload_size=max_upload_size,
        antivirus_enabled=antivirus_enabled,
        antivirus_strict_mode=antivirus_strict_mode
    )

@admin_web.route("/upload-policy", methods=["POST"])
@login_required
@admin_required
def update_upload_policy():
    custom_allowed = request.form.get("custom_allowed", "")
    custom_blocked = request.form.get("custom_blocked", "")
    max_upload_size = request.form.get("max_upload_size_mb", type=int)
    antivirus_enabled = request.form.get("antivirus_enabled") == "on"
    antivirus_strict_mode = request.form.get("antivirus_strict_mode") == "on"
    upload_policy_enabled = request.form.get("upload_policy_enabled") == "on"

    try:
        upload_policy_service.save_policy(custom_allowed, custom_blocked)
        upload_policy_service.set_enabled(upload_policy_enabled)
        if max_upload_size is not None:
            SystemStat.set_stat('global_max_upload_size_mb', max_upload_size)

        SystemStat.set_stat(antivirus_service.ENABLED_SETTING_KEY, antivirus_enabled)
        SystemStat.set_stat(antivirus_service.STRICT_MODE_SETTING_KEY, antivirus_strict_mode)

        activity_log_service.log_activity(current_user.id, 'admin_update_security_settings', metadata={
            'antivirus_enabled': antivirus_enabled,
            'antivirus_strict_mode': antivirus_strict_mode,
            'max_upload_size_mb': max_upload_size,
            'upload_policy_enabled': upload_policy_enabled
        })

        flash("Upload policy updated.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("admin.upload_policy"))

@admin_web.route("/cleanup")
@login_required
@admin_required
def cleanup():
    stats = SystemStat.get_stat('last_cleanup_stats', {
        'last_run': 'Never',
        'expired_sessions_cleaned': 0,
        'temp_files_cleaned': 0,
        'errors': []
    })
    return render_template("admin/cleanup.html", title="Admin - Storage Cleanup", stats=stats)

@admin_web.route("/cleanup/run", methods=["POST"])
@login_required
@admin_required
def run_cleanup():
    executor.submit(cleanup_storage_job)
    flash("Cleanup job queued successfully.", "success")
    return redirect(url_for('admin.cleanup'))

@admin_web.route("/diagnostics")
@login_required
@admin_required
def diagnostics():
    # Check LibreOffice
    libreoffice_bin = current_app.config.get('LIBREOFFICE_BIN')
    libreoffice_available = shutil.which(libreoffice_bin) is not None

    # Check FFmpeg
    ffmpeg_bin = Config.get_ffmpeg_bin()
    ffmpeg_available = shutil.which(ffmpeg_bin) is not None

    # Check Encryption
    encryption_available = encryption_service.is_encryption_available()

    # Check Storage
    storage_path = current_app.config.get('STORAGE_PATH')
    storage_writable = os.access(storage_path, os.W_OK) if os.path.exists(storage_path) else False

    # Upload limits
    upload_max_size = current_app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)

    # ClamAV status
    clamav_available = False
    clamav_version = "Unknown"
    clamav_error = None
    try:
        import pyclamd
        socket_path = antivirus_service.get_socket_path()
        if socket_path:
            scanner = pyclamd.ClamdUnixSocket(socket_path)
        else:
            scanner = pyclamd.ClamdNetworkSocket(
                current_app.config.get("CLAMD_HOST", "localhost"),
                current_app.config.get("CLAMD_PORT", 3310),
            )

        if scanner.ping():
            clamav_available = True
            clamav_version = scanner.version()
        else:
            clamav_error = "Ping failed"
    except Exception as e:
        clamav_error = str(e)

    # Rate limiter backend
    rate_limiter_storage = current_app.config.get('RATELIMIT_STORAGE_URI', 'memory://')

    # Background executor healthy (simple check if it exists)
    executor_healthy = executor is not None

    # Real test conversions
    lo_test_ok = False
    lo_test_error = None
    if libreoffice_available:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_txt = os.path.join(tmp_dir, "test.txt")
            with open(test_txt, "w") as f: f.write("test")
            try:
                lo_cmd = [libreoffice_bin, '--headless', '--convert-to', 'pdf', '--outdir', tmp_dir, test_txt]
                res = subprocess.run(lo_cmd, capture_output=True, timeout=10)
                lo_test_ok = res.returncode == 0 and os.path.exists(os.path.join(tmp_dir, "test.pdf"))
                if not lo_test_ok: lo_test_error = res.stderr.decode()[:200]
            except Exception as e:
                lo_test_error = str(e)

    ff_test_ok = False
    ff_test_error = None
    if ffmpeg_available:
        try:
            ff_cmd = [ffmpeg_bin, '-version']
            res = subprocess.run(ff_cmd, capture_output=True, timeout=5)
            ff_test_ok = res.returncode == 0
            if not ff_test_ok: ff_test_error = res.stderr.decode()[:200]
        except Exception as e:
            ff_test_error = str(e)

    # Get recent failures for retry
    failed_files = File.query.filter(
        (File.scan_status == 'infected') |
        (File.scan_status == 'scan_failed') |
        (File.is_quarantined == True)
    ).order_by(File.updated_at.desc()).limit(10).all()

    # Also check for office_failed
    office_failed = File.query.filter(
        File.preview_metadata.contains({'office_preview_status': 'failed'})
    ).limit(10).all()

    from app.models.zip_extract_job import ZipExtractJob
    failed_extractions = ZipExtractJob.query.filter_by(status='failed').limit(10).all()

    # Combine and deduplicate
    all_failed = {f.id: f for f in failed_files + office_failed}.values()

    diagnostics_data = {
        'failed_files': all_failed,
        'failed_extractions': failed_extractions,
        'libreoffice': {
            'status': 'Available' if lo_test_ok else ('Found but failing' if libreoffice_available else 'Not Found'),
            'path': libreoffice_bin,
            'ok': lo_test_ok,
            'error': lo_test_error
        },
        'ffmpeg': {
            'status': 'Available' if ff_test_ok else ('Found but failing' if ffmpeg_available else 'Not Found'),
            'path': ffmpeg_bin,
            'ok': ff_test_ok,
            'error': ff_test_error
        },
        'encryption': {
            'status': 'Available' if encryption_available else 'Not Available',
            'ok': encryption_available
        },
        'storage': {
            'status': 'Writable' if storage_writable else 'Not Writable',
            'path': storage_path,
            'ok': storage_writable
        },
        'uploads': {
            'max_size_mb': upload_max_size,
            'status': f'{upload_max_size} MB'
        },
        'rate_limiter': {
            'backend': rate_limiter_storage,
            'status': rate_limiter_storage
        },
        'clamav': {
            'status': 'Healthy' if clamav_available else 'Error',
            'ok': clamav_available,
            'version': clamav_version,
            'error': clamav_error,
            'connection': antivirus_service.get_connection_label(),
            'enabled': antivirus_service.is_enabled()
        },
        'executor': {
            'status': 'Healthy' if executor_healthy else 'Not Initialized',
            'ok': executor_healthy
        }
    }

    return render_template("admin/diagnostics.html", title="Admin - Diagnostics", diagnostics=diagnostics_data)

@admin_web.route("/files/<file_uuid>/retry-processing", methods=["POST"])
@login_required
@admin_required
def retry_file_processing(file_uuid):
    file_rec = File.query.filter_by(uuid=file_uuid).first()
    if not file_rec:
        abort(404)

    action = request.form.get("action", "all")

    if action == "scan":
        file_rec.scan_status = 'pending'
        db.session.commit()
        from app.services.background_jobs import scan_virus_job
        executor.submit(scan_virus_job, file_rec.id)
        flash(f"Virus scan queued for {file_rec.original_filename}", "success")
    elif action == "preview":
        from app.services.background_jobs import process_office_preview_job
        executor.submit(process_office_preview_job, file_rec.id)
        flash(f"Office preview conversion queued for {file_rec.original_filename}", "success")
    elif action == "thumbnail":
        from app.services.background_jobs import process_thumbnail_job
        executor.submit(process_thumbnail_job, file_rec.id)
        flash(f"Thumbnail generation queued for {file_rec.original_filename}", "success")
    elif action == "text":
        from app.services.background_jobs import extract_text_job
        executor.submit(extract_text_job, file_rec.id)
        flash(f"Text extraction queued for {file_rec.original_filename}", "success")
    else:
        if file_rec.is_quarantined:
            file_rec.scan_status = 'pending'
            db.session.commit()
        executor.submit(process_file_pipeline_job, file_rec.id)
        flash(f"Full reprocessing queued for {file_rec.original_filename}", "success")

    return redirect(request.referrer or url_for('admin.diagnostics'))

@admin_web.route("/diagnostics/test-clamav", methods=["POST"])
@login_required
@admin_required
def test_clamav():
    eicar_string = r'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(eicar_string.encode())
        tmp_path = tmp.name

    try:
        from app.services.antivirus_service import antivirus_service
        # We call _scan_with_clamav directly to test the daemon, bypassing local EICAR check
        # which would catch it immediately.
        from pathlib import Path
        result = antivirus_service._scan_with_clamav(Path(tmp_path))

        if result.is_infected:
            flash(f"ClamAV test SUCCESS: Threat detected as expected ({result.signature}).", "success")
        else:
            flash("ClamAV test FAILED: Threat NOT detected by daemon.", "danger")
    except Exception as e:
        flash(f"ClamAV test ERROR: {str(e)}", "danger")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return redirect(url_for('admin.diagnostics'))

@admin_web.route("/reset", methods=["POST"])
@login_required
@admin_required
def reset_system():
    mode = request.form.get("mode", "data_only")
    confirmation = request.form.get("confirmation")

    if confirmation != "RESET":
        flash("Incorrect confirmation text. Reset aborted.", "danger")
        return redirect(url_for('admin.cleanup'))

    from app.services.admin_service import admin_service
    success, message = admin_service.perform_system_reset(current_user, mode=mode)

    if success:
        flash(message, "success")
        if mode == 'full':
            # Redirect to login as other sessions might be invalidated
            from flask_login import logout_user
            logout_user()
            return redirect(url_for('auth.login'))
    else:
        flash(message, "danger")

    return redirect(url_for('admin.cleanup'))
