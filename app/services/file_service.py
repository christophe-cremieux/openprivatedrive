"""
Description: Service layer implementation for FileService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db
from app.models.file import File
from app.drive.permissions import can_access, can_delete
from app.sync.services import sync_service
from app.services.activity_log_service import activity_log_service
from app.utils.validators import validate_resource_name

class FileService:
    @staticmethod
    def get_file_by_uuid(file_uuid, user=None, action='view'):
        """Retrieves a file by its UUID and optionally checks permissions."""
        file_record = File.query.filter_by(uuid=file_uuid).first()
        if not file_record or file_record.is_deleted:
            return None

        if user:
            # Check for quarantine first for clearer error message
            if file_record.is_quarantined and not user.is_admin:
                raise PermissionError("Access denied: File is quarantined for security reasons.")

            if not can_access(user, file_record, action):
                raise PermissionError(f"User does not have {action} permission on this file.")

        return file_record

    @staticmethod
    def get_deleted_file_by_uuid(file_uuid, user):
        """Retrieves a deleted file by its UUID for the owner."""
        return File.query.filter_by(uuid=file_uuid, owner_id=user.id, is_deleted=True).first()

    @staticmethod
    def get_trash_items(user):
        """Retrieves top-level deleted files for a user."""
        deleted_files = File.query.filter(
            File.owner_id == user.id,
            File.is_deleted == True
        ).all()
        return [f for f in deleted_files if not f.folder or not f.folder.is_deleted]

    @staticmethod
    def rename_file(user, file, new_name):
        """Renames an existing file's original_filename."""
        if not can_access(user, file, 'rename'):
            raise PermissionError("User does not have permission to rename this file.")

        new_name = validate_resource_name(new_name)

        if new_name == file.original_filename:
            return file

        # Prevent duplicate sibling file names
        existing = File.query.filter_by(
            folder_id=file.folder_id,
            original_filename=new_name,
            is_deleted=False
        ).filter(File.id != file.id).first()
        if existing:
            raise ValueError(f"A file with the name '{new_name}' already exists in this location.")

        old_name = file.original_filename
        file.original_filename = new_name

        sync_service.log_event_for_all_affected(user.id, file, 'updated', {'name': new_name, 'old_name': old_name})

        db.session.commit()
        return file

    @staticmethod
    def restore_file(user, file):
        """Restores a soft-deleted file."""
        if file.owner_id != user.id and not user.is_admin:
            raise PermissionError("Only the owner can restore a file.")

        file.is_deleted = False
        file.deleted_at = None

        sync_service.log_event_for_all_affected(user.id, file, 'created', {'restored': True})
        activity_log_service.log_activity(user.id, 'restore_file', 'file', file.id)

        db.session.commit()
        return file

    @staticmethod
    def permanent_delete_file(user, file):
        """Permanently deletes a file from DB and storage, including generated previews."""
        if file.owner_id != user.id and not user.is_admin:
            raise PermissionError("Only the owner can permanently delete a file.")

        from app.services.storage_service import storage_service

        # 1. Delete original file
        storage_service.delete_file(file.storage_path)

        # 2. Delete generated thumbnails and Office previews
        metadata = file.preview_metadata or {}

        # Thumbnails
        thumbnails = metadata.get('thumbnails', {})
        for size in thumbnails:
            storage_service.delete_file(thumbnails[size])

        # Office preview
        office_path = metadata.get('office_preview_path')
        if office_path:
            storage_service.delete_file(office_path)

        file_id = file.id
        db.session.delete(file)

        activity_log_service.log_activity(user.id, 'permanent_delete_file', 'file', file_id)

        db.session.commit()

    @staticmethod
    def move_file(user, file, new_folder):
        """Moves a file to a new folder."""
        if not can_access(user, file, 'move'):
            raise PermissionError("User does not have permission to move this file.")

        from app.drive.permissions import can_upload_to_folder
        if not can_upload_to_folder(user, new_folder):
            raise PermissionError("User does not have permission to move files to the destination folder.")

        if file.folder_id == new_folder.id:
            return file

        # Prevent duplicate sibling file names
        existing = File.query.filter_by(
            folder_id=new_folder.id,
            original_filename=file.original_filename,
            is_deleted=False
        ).first()
        if existing:
            raise ValueError(f"A file with the name '{file.original_filename}' already exists in the destination.")

        old_folder_id = file.folder_id
        old_folder_uuid = file.folder.uuid if file.folder else None

        file.folder_id = new_folder.id

        # Log sync events for old and new parents
        sync_service.log_event_for_all_affected(user.id, file, 'moved', {
            'old_parent_uuid': old_folder_uuid,
            'new_parent_uuid': new_folder.uuid
        })

        activity_log_service.log_activity(user.id, 'move_file', 'file', file.id, {
            'old_folder_id': old_folder_id,
            'new_folder_id': new_folder.id
        })

        db.session.commit()
        return file

    @staticmethod
    def copy_file(user, file, target_folder):
        """Copies a file to a target folder."""
        if not can_access(user, file, 'view'): # Need view/download permission to copy
            raise PermissionError("User does not have permission to access this file.")

        from app.drive.permissions import can_upload_to_folder
        if not can_upload_to_folder(user, target_folder):
            raise PermissionError("User does not have permission to copy files to the target folder.")

        # Handle name duplication by appending "(Copy)" if necessary
        base_name = file.original_filename
        name = base_name
        counter = 1
        while True:
            existing = File.query.filter_by(
                folder_id=target_folder.id,
                original_filename=name,
                is_deleted=False
            ).first()
            if not existing:
                break

            if '.' in base_name:
                parts = base_name.rsplit('.', 1)
                name = f"{parts[0]} (Copy {counter}).{parts[1]}"
            else:
                name = f"{base_name} (Copy {counter})"
            counter += 1

        new_uuid = str(uuid.uuid4())
        from app.services.storage_service import storage_service
        new_storage_path = storage_service.backend.copy(file.storage_path, new_uuid)

        # Reset preview metadata for the new copy
        clean_metadata = dict(file.preview_metadata or {})
        clean_metadata.pop('thumbnails', None)
        clean_metadata['thumbnail_status'] = 'none'
        clean_metadata.pop('office_preview_path', None)
        clean_metadata.pop('office_preview_status', None)
        clean_metadata.pop('office_preview_error', None)

        new_file = File(
            uuid=new_uuid,
            owner_id=user.id,
            folder_id=target_folder.id,
            original_filename=name,
            stored_filename=f"{new_uuid}{file.extension or ''}",
            extension=file.extension,
            mime_type=file.mime_type,
            size_bytes=file.size_bytes,
            sha256_hash=file.sha256_hash,
            storage_path=new_storage_path,
            version_number=1,
            preview_metadata=clean_metadata,
            is_encrypted=file.is_encrypted,
            encryption_version=file.encryption_version,
            encryption_kdf=file.encryption_kdf,
            encryption_salt=file.encryption_salt,
            encryption_nonce=file.encryption_nonce,
            encryption_metadata=file.encryption_metadata
        )
        db.session.add(new_file)
        db.session.flush()

        # Trigger background jobs for the new copy
        from flask import current_app
        if not current_app.testing:
            from app.services.background_jobs import process_file_pipeline_job
            from app.extensions import executor
            executor.submit(process_file_pipeline_job, new_file.id, current_app._get_current_object())

        sync_service.log_event_for_all_affected(user.id, new_file, 'created', {
            'name': name,
            'parent_id': new_file.folder_id,
            'copied_from_uuid': file.uuid
        })

        activity_log_service.log_activity(user.id, 'copy_file', 'file', new_file.id, {
            'source_file_id': file.id,
            'target_folder_id': target_folder.id
        })

        db.session.commit()
        return new_file

    @staticmethod
    def search_files(user, query=None, mime_type=None, owner_username=None, is_starred=None, date_from=None, date_to=None, page=None, per_page=50):
        """Searches for files based on various criteria with ranking and pagination."""
        from app.models.user import User
        from app.drive.permissions import get_effective_permission, VIEWER

        filters = [File.is_deleted == False]

        if query:
            from sqlalchemy import or_, and_
            filters.append(or_(
                File.original_filename.ilike(f"%{query}%"),
                # Search within extracted text in JSON metadata only for non-encrypted files
                and_(
                    File.is_encrypted == False,
                    db.func.json_extract(File.preview_metadata, '$.extracted_text').ilike(f"%{query}%")
                )
            ))

        if mime_type:
            filters.append(File.mime_type.ilike(f"%{mime_type}%"))

        if is_starred is not None:
            filters.append(File.is_starred == is_starred)

        if date_from:
            filters.append(File.created_at >= date_from)
        if date_to:
            filters.append(File.created_at <= date_to)

        if owner_username:
            filters.append(File.owner.has(db.func.lower(User.username) == owner_username.lower()))

        # Base query for files owned by user
        owned_query = File.query.filter(File.owner_id == user.id, *filters)

        # Folders shared with user (including inherited)
        from app.sharing.services import sharing_service
        shared_resources = sharing_service.list_shared_with_user(user)

        shared_file_ids = [r['resource'].id for r in shared_resources if r['resource_type'] == 'file']
        shared_folder_ids = [r['resource'].id for r in shared_resources if r['resource_type'] == 'folder']

        # Files in shared folders (inherited)
        inherited_file_ids = []
        if shared_folder_ids:
            from app.services.folder_service import folder_service
            all_accessible_folder_ids = []
            for fid in shared_folder_ids:
                all_accessible_folder_ids.append(fid)
                all_accessible_folder_ids.extend(folder_service._get_all_descendant_ids(fid))

            inherited_files = db.session.query(File.id).filter(
                File.folder_id.in_(all_accessible_folder_ids),
                File.is_deleted == False
            ).all()
            inherited_file_ids = [f[0] for f in inherited_files]

        all_accessible_file_ids = set(shared_file_ids) | set(inherited_file_ids)
        shared_query = File.query.filter(File.id.in_(all_accessible_file_ids), *filters)

        union_query = owned_query.union(shared_query)

        # Ranking and Ordering
        if query:
            from sqlalchemy import case
            q_lower = f"%{query.lower()}%"
            # Lower score is better (higher rank)
            union_query = union_query.order_by(
                case((File.original_filename.ilike(q_lower), 0), else_=1),
                File.created_at.desc()
            )
        else:
            union_query = union_query.order_by(File.created_at.desc())

        # Pagination
        if page:
            union_query = union_query.limit(per_page).offset((page - 1) * per_page)

        return union_query.all()

    @staticmethod
    def get_recent_files(user, limit=50):
        """Retrieves recently updated files for a user."""
        return File.query.filter_by(owner_id=user.id, is_deleted=False).order_by(File.updated_at.desc()).limit(limit).all()

    @staticmethod
    def toggle_star(user, file):
        """Toggles the starred status of a file."""
        if not can_access(user, file, 'view'):
            raise PermissionError("User does not have permission to access this file.")

        file.is_starred = not file.is_starred
        db.session.commit()
        return file.is_starred

    @staticmethod
    def get_user_storage_stats(user):
        """Calculates storage usage stats for a single user."""
        usage = db.session.query(db.func.sum(File.size_bytes)).filter(
            File.owner_id == user.id,
            File.is_deleted == False
        ).scalar() or 0

        percent = (usage / user.storage_quota_bytes * 100) if user.storage_quota_bytes > 0 else 0
        return {
            'usage_bytes': usage,
            'quota_bytes': user.storage_quota_bytes,
            'usage_percent': min(100, percent)
        }

    @staticmethod
    def delete_file(user, file_uuid, permanent=False):
        """Deletes a file, either soft or permanent."""
        if permanent:
            file_record = FileService.get_deleted_file_by_uuid(file_uuid, user)
            if not file_record:
                raise ValueError("File not found in trash")
            FileService.permanent_delete_file(user, file_record)
        else:
            file_record = FileService.get_file_by_uuid(file_uuid, user=user, action='delete')
            if not file_record:
                raise ValueError("File not found")
            FileService.soft_delete_file(user, file_record)

    @staticmethod
    def soft_delete_file(user, file):
        """Soft-deletes a file."""
        if not can_delete(user, file):
            raise PermissionError("User does not have permission to delete this file.")

        file.is_deleted = True
        file.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)

        sync_service.log_event_for_all_affected(user.id, file, 'deleted')
        activity_log_service.log_activity(user.id, 'delete_file', 'file', file.id)

        db.session.commit()
        return file

file_service = FileService()
