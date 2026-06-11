"""
Description: Provides public link service logic for link creation and validation.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import secrets
import hashlib
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.public_link import PublicLink
from app.models.folder import Folder
from app.models.file import File
from app.drive.permissions import can_access
from app.services.activity_log_service import activity_log_service

class PublicLinkService:
    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def get_link_by_uuid(link_uuid, user=None):
        """Retrieves a public link by its UUID and optionally checks ownership."""
        link = PublicLink.query.filter_by(uuid=link_uuid).first()
        if not link:
            return None

        if user and link.created_by_user_id != user.id and not user.is_admin:
            raise PermissionError("User does not have permission to access this public link.")

        return link

    @staticmethod
    def create_public_link(user, resource, password=None, one_time_password=False, expires_at=None, max_downloads=None, link_type='download', max_files=25, max_upload_size_mb=100, max_upload_size_total_mb=None):
        """Creates a new public link for a resource."""
        # Only owners/managers can create public links (using share permission for now)
        if not can_access(user, resource, 'share'):
            raise ValueError("User does not have permission to create public links for this resource.")

        if getattr(resource, 'is_encrypted', False):
            raise ValueError("This file is encrypted and cannot be shared by public link in this version.")

        if link_type == 'upload':
            if not isinstance(resource, Folder):
                raise ValueError("Upload links can only be created for folders.")
            if not password:
                raise ValueError("Password is required for upload links.")
            if not max_files or max_files <= 0:
                raise ValueError("Valid max files limit is required for upload links.")
            if not max_upload_size_mb or max_upload_size_mb <= 0:
                raise ValueError("Valid max upload size is required for upload links.")

        raw_token = secrets.token_urlsafe(32)
        token_hash = PublicLinkService._hash_token(raw_token)

        res_type = 'folder' if isinstance(resource, Folder) else 'file'

        link = PublicLink(
            resource_type=res_type,
            resource_id=resource.id,
            created_by_user_id=user.id,
            token_hash=token_hash,
            password_required=bool(password),
            one_time_password=one_time_password,
            max_downloads=max_downloads,
            expires_at=expires_at,
            link_type=link_type,
            max_files=max_files,
            max_upload_size_mb=max_upload_size_mb,
            max_upload_size_total_mb=max_upload_size_total_mb
        )

        if password:
            link.password_hash = generate_password_hash(password)

        db.session.add(link)
        db.session.commit()

        activity_log_service.log_activity(user.id, 'create_public_link', res_type, resource.id, metadata={
            'link_uuid': link.uuid,
            'link_type': link_type,
            'max_files': max_files,
            'max_upload_size_mb': max_upload_size_mb,
            'max_upload_size_total_mb': max_upload_size_total_mb
        })

        return raw_token, link

    @staticmethod
    def get_link_by_token(token):
        """Finds an active, non-expired public link by its raw token or UUID."""
        token_hash = PublicLinkService._hash_token(token)
        link = PublicLink.query.filter_by(token_hash=token_hash, is_active=True).first()

        if not link:
            # Fallback to UUID lookup to support link regeneration in the UI
            link = PublicLink.query.filter_by(uuid=token, is_active=True).first()

        if not link:
            return None

        # SQLite stores datetimes as naive, so we compare with naive now()
        # but the convention in the app is to use UTC.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = link.expires_at
        if expires_at and expires_at.tzinfo:
            expires_at = expires_at.replace(tzinfo=None)

        if expires_at and expires_at < now:
            return None

        if link.max_downloads and link.download_count >= link.max_downloads:
            return None

        if link.link_type == 'upload':
            upload_count = link.upload_count or 0
            uploaded_bytes = link.uploaded_bytes or 0

            if link.max_files and upload_count >= link.max_files:
                return None
            if link.max_upload_size_total_mb and uploaded_bytes >= link.max_upload_size_total_mb * 1024 * 1024:
                return None

        return link

    @staticmethod
    def validate_password(link, password):
        """Validates the password for a password-protected link."""
        if not link.password_required:
            return True
        if not password:
            return False
        return check_password_hash(link.password_hash, password)

    @staticmethod
    def increment_download_count(link, size_bytes=0, file_count=1, commit=True):
        """Increments download count and handles one-time link logic."""
        if link.link_type == 'upload':
            link.upload_count = (link.upload_count or 0) + file_count
            link.uploaded_bytes = (link.uploaded_bytes or 0) + size_bytes
        else:
            link.download_count = (link.download_count or 0) + 1

        link.last_accessed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # One-time use logic: deactivate after first successful use
        if link.one_time_password:
            link.is_active = False

        # One-time download logic (max_downloads = 1)
        if link.max_downloads == 1:
            link.is_active = False

        if commit:
            db.session.commit()

    @staticmethod
    def handle_public_upload_transaction(link_id, files, folder, owner, uploader_ip, total_size):
        """
        Encapsulates the transactional logic for public uploads, including row locking,
        limit re-verification, and storage cleanup on failure.
        """
        from app.services.upload_service import upload_service
        from app.services.storage_service import storage_service
        from app.services.activity_log_service import activity_log_service
        from app.models.public_link import PublicLink

        uploaded_paths = []
        try:
            with db.session.begin_nested() as sp:
                # 1. Lock link to prevent race conditions on upload_count/uploaded_bytes
                locked_link = PublicLink.query.filter_by(id=link_id).with_for_update().first()
                if not locked_link:
                    raise ValueError("Public link not found.")

                # 2. Re-verify cumulative and global limits inside the transaction
                from app.models.system_stat import SystemStat
                global_limit_mb = SystemStat.get_stat('global_max_upload_size_mb', 0)
                if global_limit_mb > 0 and total_size > global_limit_mb * 1024 * 1024:
                    raise ValueError(f"Total upload size exceeds global limit of {global_limit_mb}MB.")

                curr_count = locked_link.upload_count or 0
                curr_bytes = locked_link.uploaded_bytes or 0

                if curr_count + len(files) > locked_link.max_files:
                    raise ValueError(f"Maximum {locked_link.max_files} files allowed. Currently at {curr_count}.")

                if locked_link.max_upload_size_total_mb:
                    cumulative_limit = locked_link.max_upload_size_total_mb * 1024 * 1024
                    if curr_bytes + total_size > cumulative_limit:
                        raise ValueError("Cumulative upload limit reached.")

                # 3. Process uploads one by one
                for file_obj in files:
                    new_file = upload_service.process_upload(owner, folder, file_obj, commit=False)
                    uploaded_paths.append(new_file.storage_path)

                # 4. Increment counters (commit=False as we are in a transaction)
                public_link_service.increment_download_count(locked_link, size_bytes=total_size, file_count=len(files), commit=False)

                # 5. Log activity
                activity_log_service.log_activity(None, 'public_upload_success', 'folder', folder.id, metadata={
                    'link_uuid': locked_link.uuid,
                    'file_count': len(files),
                    'total_bytes': total_size,
                    'uploader_ip': uploader_ip
                }, commit=False)
        except Exception as e:
            # Clean up any files that were already saved to storage if the transaction fails
            # Use a list of string paths to avoid ObjectDeletedError after rollback
            for path in uploaded_paths:
                try:
                    storage_service.delete_file(path)
                except Exception:
                    pass # Best effort cleanup
            raise e

public_link_service = PublicLinkService()
