"""
Description: Service layer implementation for UploadService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import hashlib
import uuid
import mimetypes
import tempfile
import shutil
from datetime import datetime, timezone
from app.extensions import db
from app.models.file import File
from app.models.folder import Folder
from app.services.storage_service import storage_service
from app.sync.services import sync_service
from app.services.activity_log_service import activity_log_service
from app.services.encryption_service import encryption_service
from app.services.upload_policy_service import upload_policy_service
from app.utils.validators import validate_file_signature, validate_resource_name
from PIL import Image
from pypdf import PdfReader
import io

class UploadService:
    @staticmethod
    def process_upload(user, folder, file_obj, filename=None, is_encrypted=False, password=None, commit=True, submit_job=True):
        """
        Processes a file upload: validates, hashes, checks quota, and saves.
        file_obj is a Werkzeug FileStorage object OR bytes (for testing).
        """
        from flask import current_app, request

        # Apply folder encryption policy if not explicitly set
        if not is_encrypted and folder and folder.encrypt_new_uploads:
            if password:
                is_encrypted = True
            else:
                raise ValueError("This folder requires encryption for new uploads, but no password was provided.")
        if filename is None:
            filename = getattr(file_obj, 'filename', 'unnamed')

        # Security: Clean filename to prevent path traversal
        filename = os.path.basename(filename)
        filename = validate_resource_name(filename)

        # Prevent duplicate sibling file names
        existing = File.query.filter_by(
            folder_id=folder.id if folder else None,
            original_filename=filename,
            is_deleted=False
        ).first()
        if existing:
            raise ValueError(f"A file with the name '{filename}' already exists in this folder.")

        extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        # 1. Extension validation
        upload_policy_service.validate_extension(extension)

        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or 'application/octet-stream'

        # 2. Stream and process
        sha256 = hashlib.sha256()
        size = 0
        file_uuid = str(uuid.uuid4())

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            try:
                if hasattr(file_obj, 'read'):
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)

                    # Read in chunks
                    chunk_size = 4096
                    while True:
                        chunk = file_obj.read(chunk_size)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        size += len(chunk)
                        tmp.write(chunk)
                else:
                    # Assume bytes
                    sha256.update(file_obj)
                    size = len(file_obj)
                    tmp.write(file_obj)

                tmp.flush()

                # Signature validation
                with open(tmp_path, 'rb') as f:
                    validate_file_signature(f, filename, mime_type)

                # Encryption
                enc_res = None
                if is_encrypted:
                    if not password:
                        raise ValueError("Password is required for encrypted uploads.")
                    if len(password) < current_app.config.get('ENCRYPTION_MIN_PASSWORD_LENGTH', 12):
                        raise ValueError(f"Password must be at least {current_app.config.get('ENCRYPTION_MIN_PASSWORD_LENGTH', 12)} characters.")

                    enc_tmp_path = tmp_path + ".enc"
                    try:
                        with open(tmp_path, 'rb') as f_in, open(enc_tmp_path, 'wb') as f_out:
                            enc_res = encryption_service.encrypt_stream(
                                f_in, f_out, password,
                                n=current_app.config.get('ENCRYPTION_KDF_N', 32768),
                                r=current_app.config.get('ENCRYPTION_KDF_R', 8),
                                p=current_app.config.get('ENCRYPTION_KDF_P', 1)
                            )
                            f_out.flush()

                        # Re-calculate hash and size for encrypted file
                        sha256 = hashlib.sha256()
                        size = 0
                        with open(enc_tmp_path, 'rb') as f_enc:
                            while True:
                                chunk = f_enc.read(4096)
                                if not chunk:
                                    break
                                sha256.update(chunk)
                                size += len(chunk)

                        # Replace tmp_path with encrypted one for storage
                        os.remove(tmp_path)
                        tmp_path = enc_tmp_path

                    except Exception as e:
                        if os.path.exists(enc_tmp_path):
                            os.remove(enc_tmp_path)
                        raise e

                # 3. Size and Quota enforcement
                from app.models.system_stat import SystemStat
                global_limit_mb = SystemStat.get_stat('global_max_upload_size_mb', 0)
                if global_limit_mb > 0 and size > global_limit_mb * 1024 * 1024:
                    raise ValueError(f"File exceeds global upload limit of {global_limit_mb}MB.")

                current_usage = db.session.query(db.func.sum(File.size_bytes)).filter_by(owner_id=user.id, is_deleted=False).scalar() or 0

                # Check if current_usage + size exceeds quota
                # Note: In bulk upload, this doesn't account for other files in the same batch yet
                # but it's a good per-file check.
                if current_usage + size > user.storage_quota_bytes:
                    quota_mb = user.storage_quota_bytes / (1024 * 1024)
                    usage_mb = current_usage / (1024 * 1024)
                    size_mb = size / (1024 * 1024)
                    raise ValueError(f"Storage quota exceeded. (Available: {max(0, quota_mb - usage_mb):.1f}MB, File: {size_mb:.1f}MB)")

                # 4. Extract Preview Metadata
                preview_metadata = None
                if not is_encrypted:
                    try:
                        if mime_type.startswith('image/'):
                            with Image.open(tmp_path) as img:
                                preview_metadata = {
                                    'width': img.width,
                                    'height': img.height,
                                    'format': img.format
                                }
                        elif mime_type == 'application/pdf':
                            reader = PdfReader(tmp_path)
                            preview_metadata = {
                                'pages': len(reader.pages)
                            }
                        elif mime_type == 'text/plain' and size < 1024 * 10: # Small text files
                            with open(tmp_path, 'r', encoding='utf-8', errors='ignore') as f:
                                preview_metadata = {
                                    'text_preview': f.read(500) # First 500 chars
                                }
                    except Exception as e:
                        current_app.logger.error(f"Metadata extraction failed for {filename}: {e}")

                # 5. Save file via storage service
                with open(tmp_path, 'rb') as f:
                    rel_path = storage_service.save_file(file_uuid, f)

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        file_hash = sha256.hexdigest()

        # 5. Create File database record
        new_file = File(
            uuid=file_uuid,
            owner_id=user.id,
            folder_id=folder.id if folder else None,
            original_filename=filename,
            stored_filename=f"{file_uuid}.bin",
            extension=extension,
            mime_type=mime_type or 'application/octet-stream',
            size_bytes=size,
            sha256_hash=file_hash,
            storage_path=rel_path,
            preview_metadata=preview_metadata,
            is_encrypted=is_encrypted
        )

        if is_encrypted and enc_res:
            new_file.encryption_version = "1"
            new_file.encryption_kdf = enc_res.kdf
            new_file.encryption_salt = enc_res.salt
            new_file.encryption_nonce = enc_res.nonce
            new_file.encryption_metadata = {
                "algorithm": enc_res.algorithm,
                "kdf": enc_res.kdf,
                "kdf_params": enc_res.kdf_params,
                "encrypted_original_size": enc_res.plaintext_size
            }

        db.session.add(new_file)
        db.session.flush()

        sync_service.log_event_for_all_affected(user.id, new_file, 'created', {
            'name': filename,
            'folder_id': new_file.folder_id,
            'is_encrypted': is_encrypted
        })
        activity_log_service.log_activity(user.id, 'upload_file', 'file', new_file.id, commit=False)

        # Enqueue consolidated pipeline job
        if is_encrypted:
            if commit:
                db.session.commit()
            return new_file

        # Set pending statuses
        metadata = dict(new_file.preview_metadata or {})

        # Antivirus is always pending for new non-encrypted files
        new_file.scan_status = 'pending'

        # Thumbnails/Previews
        from app.services.preview_service import preview_service
        p_type = preview_service.get_preview_type(new_file)

        if new_file.mime_type.startswith('image/') or \
           new_file.mime_type == 'application/pdf' or \
           new_file.mime_type.startswith('video/'):
            metadata['thumbnail_status'] = 'pending'

        if p_type in ['office_none', 'office_pending']:
            metadata['office_preview_status'] = 'pending'

        new_file.preview_metadata = metadata

        if commit:
            db.session.commit()
        else:
            db.session.flush()

        if submit_job:
            from app.extensions import executor
            from app.services.background_jobs import process_file_pipeline_job
            try:
                executor.submit(process_file_pipeline_job, new_file.id, current_app._get_current_object())
            except Exception as e:
                 current_app.logger.error(f"Failed to submit background pipeline for file {new_file.id}: {e}")

        return new_file

    @staticmethod
    def _get_or_create_subfolder(user, parent_folder, subfolder_name, commit=True):
        """Helper to find or create a subfolder by name. Owner-agnostic for shared folders."""
        existing = Folder.query.filter_by(
            parent_id=parent_folder.id if parent_folder else None,
            name=subfolder_name,
            is_deleted=False
        ).first()

        if existing:
            return existing

        # Create new subfolder
        from app.services.folder_service import folder_service
        return folder_service.create_folder(user, parent_folder, subfolder_name, commit=commit)

    @staticmethod
    def process_bulk_upload(user, base_folder, files, prefix=None, relative_paths=None, is_encrypted=False, password=None):
        """
        Processes multiple file uploads.
        Returns a tuple: (uploaded_files_list, errors_list)
        """
        from flask import current_app
        uploaded_files = []
        errors = []

        current_app.logger.info(f"Bulk Upload: Starting batch of {len(files)} files for user {user.username}")

        # We process uploads in a loop.
        # We collect background jobs to submit them AFTER the loop to avoid I/O closed issues
        # with Werkzeug's SpooledTemporaryFile when threads are spawned during request processing.
        jobs_to_submit = []

        for i, file_obj in enumerate(files):
            original_name = getattr(file_obj, 'filename', f"file_{i}")
            target_folder = base_folder

            try:
                # 1. Handle directory structure if relative_paths provided
                if relative_paths and i < len(relative_paths):
                    rel_path = relative_paths[i]
                    path_parts = rel_path.split('/')[:-1] # Remove filename
                    for part in path_parts:
                        if part:
                            # Use commit=True for folder creation to ensure it's visible for next files
                            target_folder = UploadService._get_or_create_subfolder(user, target_folder, part, commit=True)

                # 2. Handle sequential renaming if prefix provided
                target_filename = original_name
                if prefix:
                    ext = original_name.rsplit('.', 1)[1] if '.' in original_name else ''
                    # Example: prefix_001.jpg
                    target_filename = f"{prefix}_{str(i+1).zfill(3)}"
                    if ext:
                        target_filename += f".{ext}"

                # 3. Process single upload
                # Use commit=True to fix the "Scanning" status race condition.
                # Use submit_job=False here, we'll submit them all at the end of the loop.
                new_file = UploadService.process_upload(
                    user, target_folder, file_obj,
                    filename=target_filename,
                    is_encrypted=is_encrypted,
                    password=password,
                    commit=True,
                    submit_job=False
                )
                uploaded_files.append(new_file)
                if not new_file.is_encrypted:
                    jobs_to_submit.append(new_file.id)

                current_app.logger.info(f"Bulk Upload: Successfully processed {original_name} ({i+1}/{len(files)})")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Bulk Upload: Error processing {original_name} ({i+1}/{len(files)}): {str(e)}")
                errors.append(f"File '{original_name}': {str(e)}")

        # Submit background jobs after all files have been read and processed
        if jobs_to_submit:
            from app.extensions import executor
            from app.services.background_jobs import process_file_pipeline_job
            app_obj = current_app._get_current_object()
            for fid in jobs_to_submit:
                try:
                    executor.submit(process_file_pipeline_job, fid, app_obj)
                except Exception as e:
                    current_app.logger.error(f"Bulk Upload: Failed to submit background pipeline for file {fid}: {e}")

        current_app.logger.info(f"Bulk Upload: Completed batch. Success: {len(uploaded_files)}, Errors: {len(errors)}")
        return uploaded_files, errors


upload_service = UploadService()
