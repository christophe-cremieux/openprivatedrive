"""
Description: Implements service layer logic for background jobs.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import time
import os
import io
import tempfile
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from PIL import Image
from flask import current_app
from app.extensions import executor, db
from app.models.file import File
from app.models.folder import Folder
from app.models.system_stat import SystemStat
from app.services.storage_service import storage_service
from app.config import Config

def process_thumbnail_job(file_id, app=None):
    """Generates thumbnails for image files and PDFs."""
    from app import create_app

    if not app:
        app = create_app()

    with app.app_context():
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            current_app.logger.warning(f"Background Job: File {file_id} not found in database for thumbnail generation")
            return

        if getattr(file_rec, 'is_encrypted', False):
            return

        is_image = file_rec.mime_type.startswith('image/')
        is_pdf = file_rec.mime_type == 'application/pdf'
        is_video = file_rec.mime_type.startswith('video/')

        # Check if it's an Office document that has a generated PDF
        office_pdf_path = None
        if not is_image and not is_pdf and not is_video:
            metadata = file_rec.preview_metadata or {}
            if metadata.get('office_preview_status') == 'ready':
                office_pdf_path = metadata.get('office_preview_path')

        if not is_image and not is_pdf and not is_video and not office_pdf_path:
            return

        current_app.logger.info(f"Background Job: Generating thumbnails for {file_rec.original_filename}")

        try:
            if is_image:
                source_path = storage_service.get_full_path(file_rec.storage_path)
                if not os.path.exists(source_path):
                    current_app.logger.error(f"Source file not found: {source_path}")
                    return
                img = Image.open(source_path)
            elif is_video:
                # Video thumbnail using ffmpeg
                source_path = storage_service.get_full_path(file_rec.storage_path)
                from app.config import Config
                ffmpeg_bin = Config.get_ffmpeg_bin()
                if not os.path.exists(ffmpeg_bin):
                    current_app.logger.warning(f"ffmpeg not found at {ffmpeg_bin}, skipping video thumbnail")
                    return

                with tempfile.TemporaryDirectory() as tmp_dir:
                    thumb_out = os.path.join(tmp_dir, "thumb.webp")
                    # Capture frame at 1 second mark
                    import subprocess
                    cmd = [
                        ffmpeg_bin, '-y', '-i', source_path,
                        '-ss', '00:00:01', '-vframes', '1',
                        '-filter:v', 'scale=640:-1',
                        thumb_out
                    ]
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode != 0:
                        current_app.logger.error(f"ffmpeg failed: {result.stderr.decode()}")
                        return

                    if not os.path.exists(thumb_out):
                        return

                    img = Image.open(thumb_out)
                    # We need to copy to memory because we're about to exit TemporaryDirectory
                    img_data = io.BytesIO()
                    img.save(img_data, format="WEBP")
                    img.close()
                    img_data.seek(0)
                    img = Image.open(img_data)
            else:
                # PDF or Office PDF
                source_path = storage_service.get_full_path(office_pdf_path if office_pdf_path else file_rec.storage_path)
                if not os.path.exists(source_path):
                    current_app.logger.error(f"Source PDF file not found: {source_path}")
                    return

                import fitz # PyMuPDF
                doc = fitz.open(source_path)
                if doc.page_count == 0:
                    current_app.logger.error(f"PDF file has no pages: {source_path}")
                    doc.close()
                    return

                page = doc.load_page(0)
                pix = page.get_pixmap(alpha=False)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                doc.close()

            # Ensure it's RGB for webp
            if img.mode in ("RGBA", "P", "CMYK"):
                img = img.convert("RGB")

            thumbnails = {}
            for size_name, size in [('small', (96, 96)), ('medium', (192, 192)), ('large', (320, 240))]:
                thumb = img.copy()
                thumb.thumbnail(size, Image.Resampling.LANCZOS)

                rel_thumb_path = storage_service.generate_thumbnail_path(file_rec.uuid, size_name)
                full_thumb_path = storage_service.get_full_path(rel_thumb_path)

                # Ensure directory exists
                os.makedirs(os.path.dirname(full_thumb_path), exist_ok=True)

                thumb.save(full_thumb_path, "WEBP", quality=85)
                thumbnails[size_name] = rel_thumb_path

            img.close()

            # Update metadata
            metadata = dict(file_rec.preview_metadata or {})
            metadata['thumbnails'] = thumbnails
            metadata['thumbnail_status'] = 'ready'
            file_rec.preview_metadata = metadata

            db.session.commit()
            current_app.logger.info(f"Background Job: Thumbnails for {file_rec.original_filename} completed")

        except Exception as e:
            current_app.logger.error(f"Failed to generate thumbnail for {file_id}: {e}")
            if file_rec:
                metadata = dict(file_rec.preview_metadata or {})
                metadata['thumbnail_status'] = 'failed'
                file_rec.preview_metadata = metadata
                db.session.commit()

def process_office_preview_job(file_id, app=None):
    """Converts Office/LibreOffice documents to PDF for preview."""
    from app import create_app

    if not app:
        app = create_app()

    with app.app_context():
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            current_app.logger.warning(f"Background Job: File {file_id} not found in database for office preview")
            return

        if file_rec.is_quarantined:
            return

        if getattr(file_rec, 'is_encrypted', False):
            return

        if not current_app.config.get('OFFICE_PREVIEW_ENABLED'):
            return

        # Check if file size is under limit
        max_size = current_app.config.get('OFFICE_PREVIEW_MAX_MB', 50) * 1024 * 1024
        if file_rec.size_bytes > max_size:
            metadata = dict(file_rec.preview_metadata or {})
            metadata['office_preview_status'] = 'unsupported'
            metadata['office_preview_error'] = 'File too large'
            file_rec.preview_metadata = metadata
            db.session.commit()
            return

        current_app.logger.info(f"Background Job: Generating Office preview for {file_rec.original_filename}")

        # Update status to pending
        metadata = dict(file_rec.preview_metadata or {})
        metadata['office_preview_status'] = 'pending'
        file_rec.preview_metadata = metadata
        db.session.commit()

        source_path = storage_service.get_full_path(file_rec.storage_path)
        if not os.path.exists(source_path):
            current_app.logger.error(f"Source file not found: {source_path}")
            return

        libreoffice_bin = current_app.config.get('LIBREOFFICE_BIN', '/usr/bin/libreoffice')
        if not os.path.exists(libreoffice_bin):
            current_app.logger.error(f"LibreOffice binary not found at {libreoffice_bin}")
            metadata = dict(file_rec.preview_metadata or {})
            metadata['office_preview_status'] = 'failed'
            metadata['office_preview_error'] = 'LibreOffice not found'
            file_rec.preview_metadata = metadata
            db.session.commit()
            return

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # We need to copy the file to the temp dir with its original extension for LibreOffice to recognize it
                _, ext = os.path.splitext(file_rec.original_filename)
                input_file = os.path.join(tmp_dir, f"input{ext}")
                shutil.copy2(source_path, input_file)

                # Set a unique LibreOffice profile per conversion to avoid concurrency issues
                user_install_dir = os.path.join(tmp_dir, "libreoffice_profile")
                os.makedirs(user_install_dir, exist_ok=True)

                timeout = current_app.config.get('OFFICE_PREVIEW_TIMEOUT_SECONDS', 30)

                # Run LibreOffice headless conversion
                cmd = [
                    libreoffice_bin,
                    '--headless',
                    f'-env:UserInstallation=file://{user_install_dir}',
                    '--nologo',
                    '--nofirststartwizard',
                    '--nodefault',
                    '--nolockcheck',
                    '--convert-to', 'pdf',
                    '--outdir', tmp_dir,
                    input_file
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=timeout)

                if result.returncode != 0:
                    err_msg = result.stderr.decode()
                    raise Exception(f"LibreOffice failed with exit code {result.returncode}: {err_msg[:500]}")

                generated_pdf = os.path.join(tmp_dir, "input.pdf")
                if not os.path.exists(generated_pdf):
                    raise Exception("LibreOffice did not generate a PDF file")

                rel_preview_path = storage_service.generate_preview_path(file_rec.uuid)
                full_preview_path = storage_service.get_full_path(rel_preview_path)

                os.makedirs(os.path.dirname(full_preview_path), exist_ok=True)
                shutil.move(generated_pdf, full_preview_path)

                # Update metadata
                metadata = dict(file_rec.preview_metadata or {})
                metadata['office_preview_status'] = 'ready'
                metadata['office_preview_type'] = 'pdf'
                metadata['office_preview_path'] = rel_preview_path
                metadata['office_preview_error'] = None
                file_rec.preview_metadata = metadata
                db.session.commit()

                current_app.logger.info(f"Background Job: Office preview for {file_rec.original_filename} completed")

                # Chain thumbnail generation for Office document
                process_thumbnail_job(file_id, app)

            except Exception as e:
                current_app.logger.error(f"Failed to generate office preview for {file_id}: {e}")
                metadata = dict(file_rec.preview_metadata or {})
                metadata['office_preview_status'] = 'failed'
                metadata['office_preview_error'] = str(e)[:500]
                file_rec.preview_metadata = metadata
                db.session.commit()

def extract_text_job(file_id, app=None):
    """Best-effort text extraction for search index."""
    from app import create_app

    if not app:
        app = create_app()

    with app.app_context():
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            current_app.logger.warning(f"Background Job: File {file_id} not found in database for text extraction")
            return

        if getattr(file_rec, 'is_encrypted', False):
            return

        mime = file_rec.mime_type
        full_path = storage_service.get_full_path(file_rec.storage_path)
        if not os.path.exists(full_path):
            return

        extracted_text = ""
        try:
            if mime == 'application/pdf':
                from pypdf import PdfReader
                reader = PdfReader(full_path)
                # Limit to first 20 pages or so to be reasonable
                for i in range(min(len(reader.pages), 20)):
                    extracted_text += reader.pages[i].extract_text() + "\n"

            elif 'officedocument.wordprocessingml' in mime or 'word' in mime:
                import docx
                doc = docx.Document(full_path)
                extracted_text = "\n".join([p.text for p in doc.paragraphs])

            elif 'officedocument.spreadsheetml' in mime or 'excel' in mime:
                import openpyxl
                wb = openpyxl.load_workbook(full_path, data_only=True, read_only=True)
                for sheet in wb.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        extracted_text += " ".join([str(c) for c in row if c is not None]) + "\n"

            elif 'oasis.opendocument.text' in mime:
                from odf import text, teletype, opendocument
                odt = opendocument.load(full_path)
                all_paragraphs = odt.getElementsByType(text.P)
                extracted_text = "\n".join([teletype.get_string(p) for p in all_paragraphs])

            elif 'oasis.opendocument.spreadsheet' in mime:
                from odf import table, teletype, opendocument
                ods = opendocument.load(full_path)
                all_rows = ods.getElementsByType(table.TableRow)
                for row in all_rows:
                    cells = row.getElementsByType(table.TableCell)
                    extracted_text += " ".join([teletype.get_string(c) for c in cells]) + "\n"

            elif mime.startswith('text/'):
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    extracted_text = f.read(100000) # 100KB max

            if extracted_text:
                metadata = dict(file_rec.preview_metadata or {})
                # Limit stored index text size to avoid bloating DB
                metadata['extracted_text'] = extracted_text[:200000]
                file_rec.preview_metadata = metadata
                db.session.commit()
                current_app.logger.info(f"Background Job: Text extracted for {file_rec.original_filename}")

        except Exception as e:
            current_app.logger.error(f"Failed to extract text for {file_id}: {e}")

def scan_virus_job(file_id, app=None):
    """Performs a quarantine and antivirus scan on a file."""
    from app import create_app
    from app.services.antivirus_service import antivirus_service

    if not app:
        app = create_app()

    with app.app_context():
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            current_app.logger.warning(f"Background Job: File {file_id} not found in database for virus scan")
            return

        current_app.logger.info(f"Background Job: Running quarantine scan for file {file_rec.original_filename} (id={file_id})")

        full_path = storage_service.get_full_path(file_rec.storage_path)
        try:
            scan_result = antivirus_service.scan_file(full_path, file_rec.original_filename)
        except Exception as e:
            error_msg = str(e)
            current_app.logger.error(f"Antivirus scan failed via {antivirus_service.get_connection_label()}: {error_msg}")
            file_rec.scan_status = 'scan_failed'
            file_rec.antivirus_error = error_msg
            file_rec.scanned_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            return

        file_rec.scanned_at = datetime.now(timezone.utc).replace(tzinfo=None)
        file_rec.antivirus_signature = scan_result.signature
        file_rec.antivirus_error = scan_result.error

        if scan_result.is_infected:
            current_app.logger.warning(f"Background Job: THREAT DETECTED in file {file_id}")
            if scan_result.signature:
                current_app.logger.warning(f"Antivirus signature for file {file_id}: {scan_result.signature}")
            file_rec.is_quarantined = True
            file_rec.scan_status = 'infected'
            db.session.commit()

            from app.services.activity_log_service import activity_log_service
            activity_log_service.log_activity(file_rec.owner_id, 'virus_detected', 'file', file_rec.id)
        else:
            current_app.logger.info(f"Background Job: Scan for file {file_id} passed")
            file_rec.scan_status = 'clean'
            file_rec.is_quarantined = False
            db.session.commit()

def process_file_pipeline_job(file_id, app=None):
    """Single pipeline job to avoid nested executor submissions during shutdown."""
    from app import create_app
    from app.services.preview_service import preview_service

    if not app:
        app = create_app()

    with app.app_context():
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            current_app.logger.warning(f"Background Job: File {file_id} not found in database for pipeline")
            return

        if getattr(file_rec, 'is_encrypted', False):
            return

        # 1. Virus Scan (Simulated)
        # We'll reuse the logic from scan_virus_job but inline it or call it synchronously
        scan_virus_job(file_id, app)

        # Refresh record after scan commit
        db.session.refresh(file_rec)

        if file_rec.scan_status == 'clean' and not file_rec.is_quarantined:
            # 2. Text Extraction (for PDF, Office, Text)
            if not file_rec.mime_type.startswith('image/'):
                extract_text_job(file_id, app)

            # 3. Specialized Previews
            p_type = preview_service.get_preview_type(file_rec)

            if file_rec.mime_type.startswith('image/') or \
               file_rec.mime_type == 'application/pdf' or \
               file_rec.mime_type.startswith('video/'):
                process_thumbnail_job(file_id, app)
            elif p_type in ['office_none', 'office_pending', 'office_failed']:
                process_office_preview_job(file_id, app)

def cleanup_storage_job(app=None):
    """Consolidated cleanup for expired sessions, temporary files, orphans, and logs."""
    from datetime import timedelta
    from app import create_app
    from app.services.upload_session_service import upload_session_service
    from app.models.activity_log import ActivityLog

    if not app:
        app = create_app()

    with app.app_context():
        current_app.logger.info("Background Job: Starting storage cleanup")

        cleanup_stats = {
            'last_run': datetime.now(timezone.utc).isoformat(),
            'expired_sessions_cleaned': 0,
            'temp_files_cleaned': 0,
            'orphan_files_cleaned': 0,
            'orphan_thumbnails_cleaned': 0,
            'orphan_previews_cleaned': 0,
            'logs_pruned': 0,
            'errors': []
        }

        # 1. Cleanup expired upload sessions
        try:
            expired_count = upload_session_service.cleanup_expired_sessions()
            cleanup_stats['expired_sessions_cleaned'] = expired_count
            current_app.logger.info(f"Background Job: Cleaned up {expired_count} expired upload sessions")
        except Exception as e:
            cleanup_stats['errors'].append(f"Session cleanup error: {str(e)}")

        # 2. Cleanup old temporary decrypted/zip files (older than 1 hour for decrypt, 24h for zip)
        storage_root = current_app.config['STORAGE_PATH']
        temp_dir = os.path.join(storage_root, 'temp')
        os.makedirs(temp_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(temp_dir, 0o700)
        except Exception:
            pass

        if os.path.exists(temp_dir):
            try:
                now = time.time()
                for f in os.listdir(temp_dir):
                    f_path = os.path.join(temp_dir, f)
                    if os.path.isfile(f_path):
                        # Old decrypted files (1 hour)
                        if f.startswith("decrypt_") and os.stat(f_path).st_mtime < now - 3600:
                            try:
                                os.remove(f_path)
                                cleanup_stats['temp_files_cleaned'] += 1
                            except OSError as e:
                                cleanup_stats['errors'].append(f"File delete error ({f}): {str(e)}")
                        # Old abandoned bulk downloads (24 hours)
                        elif f.startswith("bulk_download_") and os.stat(f_path).st_mtime < now - (24 * 3600):
                            try:
                                os.remove(f_path)
                                cleanup_stats['temp_files_cleaned'] += 1
                            except OSError as e:
                                cleanup_stats['errors'].append(f"File delete error ({f}): {str(e)}")
            except Exception as e:
                cleanup_stats['errors'].append(f"Temp dir walk error: {str(e)}")
                current_app.logger.error(f"Error cleaning temp directory: {e}")

        # 3. Orphan File Scanning (Files in storage not in DB)
        try:
            # We only scan 'files/', 'thumbnails/', 'previews/' subdirectories
            for sub_dir, stat_key, model_col in [
                ('files', 'orphan_files_cleaned', File.storage_path),
                ('thumbnails', 'orphan_thumbnails_cleaned', None),
                ('previews', 'orphan_previews_cleaned', None)
            ]:
                full_sub_dir = os.path.join(storage_root, sub_dir)
                if not os.path.exists(full_sub_dir):
                    continue

                # Fetch all relevant paths from DB for comparison
                if sub_dir == 'files':
                    known_paths = set(p[0] for p in db.session.query(File.storage_path).all())
                else:
                    # For thumbnails and previews, we have to extract them from JSON metadata
                    known_paths = set()
                    files_with_meta = File.query.filter(File.preview_metadata.isnot(None)).all()
                    for f in files_with_meta:
                        meta = f.preview_metadata or {}
                        if sub_dir == 'thumbnails':
                            thumbs = meta.get('thumbnails', {})
                            for t_path in thumbs.values():
                                known_paths.add(t_path)
                        elif sub_dir == 'previews':
                            p_path = meta.get('office_preview_path')
                            if p_path:
                                known_paths.add(p_path)

                # Walk the directory
                for root, dirs, files in os.walk(full_sub_dir):
                    for name in files:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, storage_root)

                        if rel_path not in known_paths:
                            # Verify it's old enough (1 hour) to avoid deleting files currently being written
                            if os.stat(full_path).st_mtime < time.time() - 3600:
                                try:
                                    os.remove(full_path)
                                    cleanup_stats[stat_key] += 1
                                except OSError as e:
                                    cleanup_stats['errors'].append(f"Orphan delete error ({rel_path}): {str(e)}")
        except Exception as e:
            cleanup_stats['errors'].append(f"Orphan scan error: {str(e)}")

        # 4. Prune old activity logs (Older than 90 days)
        try:
            retention_days = current_app.config.get('LOG_RETENTION_DAYS', 90)
            threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)
            deleted_logs = ActivityLog.query.filter(ActivityLog.created_at < threshold).delete()
            cleanup_stats['logs_pruned'] = deleted_logs
            db.session.commit()
            current_app.logger.info(f"Background Job: Pruned {deleted_logs} activity logs older than {retention_days} days")
        except Exception as e:
            db.session.rollback()
            cleanup_stats['errors'].append(f"Log pruning error: {str(e)}")

        SystemStat.set_stat('last_cleanup_stats', cleanup_stats)
        current_app.logger.info("Background Job: Storage cleanup completed")

def trash_retention_policy_job(app=None):
    """Permanently deletes items that have been in the trash for more than 30 days."""
    from app import create_app
    from app.services.folder_service import folder_service
    from app.services.file_service import file_service

    if not app:
        app = create_app()
    with app.app_context():
        current_app.logger.info("Background Job: Running trash retention policy (30 days)")
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        threshold = now_naive - timedelta(days=30)

        # 1. Find root-level deleted folders older than 30 days
        expired_folders = Folder.query.filter(
            Folder.is_deleted == True,
            Folder.deleted_at < threshold
        ).all()
        current_app.logger.info(f"Background Job: Found {len(expired_folders)} expired folders")

        for folder in expired_folders:
            # Only delete if it's a "top-level" deleted item to avoid redundant work
            if not folder.parent_id or not folder.parent.is_deleted:
                current_app.logger.info(f"Background Job: Permanently deleting expired folder: {folder.name} (ID: {folder.id})")
                try:
                    folder_service.permanent_delete_folder(folder.owner, folder)
                except Exception as e:
                    current_app.logger.error(f"Error deleting folder {folder.id}: {e}")

        # 2. Find root-level deleted files older than 30 days
        expired_files = File.query.filter(
            File.is_deleted == True,
            File.deleted_at < threshold
        ).all()
        current_app.logger.info(f"Background Job: Found {len(expired_files)} expired files")

        for file_rec in expired_files:
            if not file_rec.folder_id or not file_rec.folder.is_deleted:
                current_app.logger.info(f"Background Job: Permanently deleting expired file: {file_rec.original_filename} (ID: {file_rec.id})")
                try:
                    file_service.permanent_delete_file(file_rec.owner, file_rec)
                except Exception as e:
                    current_app.logger.error(f"Error deleting file {file_rec.id}: {e}")

        db.session.commit()
        current_app.logger.info("Background Job: Trash retention policy completed")
