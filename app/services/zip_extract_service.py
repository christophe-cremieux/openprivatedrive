"""
Description: Service layer implementation for ZipExtractService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import zipfile
import stat
from datetime import datetime, timezone
from flask import current_app
from app.extensions import db

class ZipExtractService:
    @staticmethod
    def extract_zip_background(job_uuid: str, app=None):
        """Background task for extracting ZIP."""
        from app import create_app

        if not app:
            app = create_app()

        with app.app_context():
            from app.models.zip_extract_job import ZipExtractJob
            from app.models.folder import Folder
            from app.services.upload_service import upload_service
            from app.services.folder_service import folder_service
            from app.services.storage_service import storage_service
            from app.services.activity_log_service import activity_log_service
            from app.drive.permissions import can_access, can_upload_to_folder

            job = ZipExtractJob.query.filter_by(uuid=job_uuid).first()
            if not job:
                return

            job.status = 'processing'
            job.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            summary = {
                "folders_created": 0,
                "files_created": 0,
                "files_skipped": 0,
                "errors": []
            }

            try:
                user = job.user
                zip_file_rec = job.zip_file
                dest_folder = job.destination_folder

                if zip_file_rec.is_quarantined or zip_file_rec.is_encrypted:
                    raise ValueError("Cannot extract an encrypted or quarantined ZIP file.")

                # Final permission check before starting
                if not can_access(user, zip_file_rec, 'download'):
                    raise PermissionError("Access denied to ZIP file.")
                if not can_upload_to_folder(user, dest_folder):
                    raise PermissionError("Access denied to destination folder.")

                full_path = storage_service.get_full_path(zip_file_rec.storage_path)
                if not os.path.exists(full_path):
                    raise FileNotFoundError("Physical ZIP file missing.")

                max_files = current_app.config.get('ZIP_EXTRACT_MAX_FILES', 1500)
                max_total_bytes = current_app.config.get('ZIP_EXTRACT_MAX_TOTAL_MB', 1024) * 1024 * 1024
                max_single_bytes = current_app.config.get('ZIP_EXTRACT_MAX_SINGLE_FILE_MB', 1500) * 1024 * 1024
                max_depth = current_app.config.get('ZIP_EXTRACT_MAX_DEPTH', 30)
                max_ratio = current_app.config.get('ZIP_EXTRACT_MAX_RATIO', 100) # Default 100:1

                with zipfile.ZipFile(full_path, 'r') as zf:
                    infolist = zf.infolist()

                    # 1. Pre-extraction security/limit checks
                    if len(infolist) > max_files:
                        raise ValueError(f"ZIP contains too many items (max {max_files}).")

                    total_uncompressed_size = sum(info.file_size for info in infolist)
                    if total_uncompressed_size > max_total_bytes:
                        raise ValueError(f"Total uncompressed size exceeds limit.")

                    # Track created folders to avoid repeated DB lookups
                    folder_cache = { "": dest_folder }

                    for info in infolist:
                        filename = info.filename

                        # ZIP entry sanitization
                        # 1. Component check (reject .. anywhere)
                        clean_filename = filename.replace('\\', '/')
                        if '..' in clean_filename.split('/'):
                             summary["errors"].append(f"Security: Blocked traversal component in '{filename}'")
                             summary["files_skipped"] += 1
                             continue

                        # 2. Normalize path
                        normalized_name = os.path.normpath(filename)

                        # 3. Rejections
                        is_safe = True
                        if normalized_name.startswith('..') or normalized_name.startswith('/') or normalized_name.startswith('\\'):
                             summary["errors"].append(f"Security: Blocked path traversal attempt in '{filename}'")
                             is_safe = False

                        if ':' in normalized_name: # Windows drive paths
                             summary["errors"].append(f"Security: Blocked Windows drive path in '{filename}'")
                             is_safe = False

                        mode = info.external_attr >> 16
                        if mode > 0 and stat.S_ISLNK(mode): # Symlink check
                             summary["errors"].append(f"Security: Blocked symlink in '{filename}'")
                             is_safe = False

                        # Flag 0x1 is encrypted
                        if info.flag_bits & 0x1:
                             summary["errors"].append(f"Security: Blocked encrypted entry in '{filename}'")
                             is_safe = False

                        if filename.count('/') > max_depth or filename.count('\\') > max_depth:
                            summary["errors"].append(f"Security: Path depth exceeded in '{filename}'")
                            is_safe = False

                        # Zip Bomb: compression ratio check
                        if info.compress_size > 0:
                            ratio = info.file_size / info.compress_size
                            if ratio > max_ratio:
                                summary["errors"].append(f"Security: Compression ratio too high for '{filename}'")
                                is_safe = False
                        elif info.file_size > 0:
                            # if compress_size is 0 but file_size > 0, it's suspicious
                            summary["errors"].append(f"Security: Suspicious compression metadata for '{filename}'")
                            is_safe = False

                        if not is_safe:
                            summary["files_skipped"] += 1
                            continue

                        if info.is_dir():
                            continue

                        if info.file_size > max_single_bytes:
                            summary["files_skipped"] += 1
                            summary["errors"].append(f"Limit: File '{filename}' exceeds single file size limit.")
                            continue

                        # Determine target folder based on ZIP structure
                        # Support both / and \ as separators for ZIPs created on different OS
                        clean_filename = filename.replace('\\', '/')
                        parts = clean_filename.split('/')
                        current_path = ""
                        target_folder = dest_folder
                        folder_error = False

                        for part in parts[:-1]:
                            if not part: continue
                            new_path = os.path.join(current_path, part) if current_path else part
                            if new_path not in folder_cache:
                                try:
                                    existing = Folder.query.filter_by(
                                        parent_id=target_folder.id if target_folder else None,
                                        name=part,
                                        is_deleted=False
                                    ).first()
                                    if existing:
                                        folder_cache[new_path] = existing
                                    else:
                                        folder_cache[new_path] = folder_service.create_folder(user, target_folder, part)
                                        summary["folders_created"] += 1
                                except Exception as e:
                                    summary["errors"].append(f"Folder error '{part}': {str(e)}")
                                    folder_error = True
                                    break
                            target_folder = folder_cache.get(new_path)
                            current_path = new_path

                        if folder_error or (not target_folder and len(parts) > 1):
                            summary["files_skipped"] += 1
                            continue

                        # Extract file to temp and process upload
                        actual_filename = parts[-1]
                        if not actual_filename:
                            continue

                        try:
                            with zf.open(info) as source:
                                try:
                                    # Using per-file commit to avoid DB inconsistent state and handle physical files correctly
                                    upload_service.process_upload(
                                        user, target_folder, source,
                                        filename=actual_filename,
                                        commit=True
                                    )
                                    summary["files_created"] += 1
                                except ValueError as ve:
                                    summary["files_skipped"] += 1
                                    summary["errors"].append(f"Upload error '{filename}': {str(ve)}")
                        except Exception as e:
                            summary["files_skipped"] += 1
                            summary["errors"].append(f"Extraction error '{filename}': {str(e)}")

                    job.status = 'completed' if not summary["errors"] else 'completed_with_errors'
                    activity_log_service.log_activity(user.id, 'zip_extract_completed', 'file', zip_file_rec.id, metadata=summary)

            except Exception as e:
                db.session.rollback()
                job.status = 'failed'
                job.error_message = str(e)
                summary["errors"].append(f"Critical error: {str(e)}")
                activity_log_service.log_activity(job.user_id, 'zip_extract_failed', 'file', job.zip_file_id, metadata={"error": str(e)})

            job.summary_json = summary
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

zip_extract_service = ZipExtractService()
