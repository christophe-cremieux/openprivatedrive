"""
Description: Service layer implementation for FolderService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from datetime import datetime, timezone
from flask import url_for
from sqlalchemy import literal, text, update
from app.extensions import db
from app.models.folder import Folder
from app.models.file import File
from app.models.user import User
from app.drive.permissions import can_access, can_upload_to_folder, can_delete, get_effective_permission
from app.sync.services import sync_service
from app.services.activity_log_service import activity_log_service
from app.services.preview_service import preview_service
from app.utils.validators import validate_resource_name

class FolderService:
    @staticmethod
    def create_root_folder_for_user(user):
        """Creates the root folder 'My Drive' for a new user."""
        root_folder = Folder(
            name="My Drive",
            owner_id=user.id,
            is_root=True,
            parent_id=None
        )
        db.session.add(root_folder)
        db.session.flush() # Get ID for sync event

        sync_service.log_event_for_all_affected(user.id, root_folder, 'created', {'name': root_folder.name, 'is_root': True})
        activity_log_service.log_activity(user.id, 'create_folder', 'folder', root_folder.id)

        # Session commit is handled by the caller (e.g., AuthService)
        return root_folder

    @staticmethod
    def get_user_root_folder(user):
        """Retrieves the root folder for a given user."""
        return Folder.query.filter_by(owner_id=user.id, is_root=True).first()

    @staticmethod
    def create_folder(user, parent_folder, name, commit=True):
        """Creates a new folder under a parent folder."""
        if parent_folder and not can_upload_to_folder(user, parent_folder):
            raise PermissionError("User does not have permission to create folders here.")

        name = validate_resource_name(name)

        # Prevent duplicate sibling folder names
        existing = Folder.query.filter_by(
            parent_id=parent_folder.id if parent_folder else None,
            name=name,
            is_deleted=False
        ).first()
        if existing:
            raise ValueError(f"A folder with the name '{name}' already exists in this location.")

        new_folder = Folder(
            name=name,
            owner_id=user.id,
            parent_id=parent_folder.id if parent_folder else None,
            is_root=False
        )
        db.session.add(new_folder)
        db.session.flush()

        sync_service.log_event_for_all_affected(user.id, new_folder, 'created', {'name': name, 'parent_id': new_folder.parent_id})
        activity_log_service.log_activity(user.id, 'create_folder', 'folder', new_folder.id)

        if commit:
            db.session.commit()
        return new_folder

    @staticmethod
    def get_folder_by_uuid(folder_uuid, user=None, action='view'):
        """Retrieves a folder by its UUID and optionally checks permissions."""
        folder = Folder.query.filter_by(uuid=folder_uuid).first()
        if not folder or folder.is_deleted:
            return None

        if user and not can_access(user, folder, action):
            raise PermissionError(f"User does not have {action} permission on this folder.")

        return folder

    @staticmethod
    def get_deleted_folder_by_uuid(folder_uuid, user):
        """Retrieves a deleted folder by its UUID for the owner."""
        return Folder.query.filter_by(uuid=folder_uuid, owner_id=user.id, is_deleted=True).first()

    @staticmethod
    def get_trash_items(user):
        """Retrieves top-level deleted folders for a user."""
        deleted_folders = Folder.query.filter(
            Folder.owner_id == user.id,
            Folder.is_deleted == True
        ).all()
        return [f for f in deleted_folders if not f.parent or not f.parent.is_deleted]

    @staticmethod
    def rename_folder(user, folder, new_name):
        """Renames an existing folder."""
        if not can_access(user, folder, 'rename'):
            raise PermissionError("User does not have permission to rename this folder.")

        new_name = validate_resource_name(new_name)

        if new_name == folder.name:
            return folder

        # Prevent duplicate sibling folder names
        existing = Folder.query.filter_by(
            parent_id=folder.parent_id,
            name=new_name,
            is_deleted=False
        ).filter(Folder.id != folder.id).first()
        if existing:
            raise ValueError(f"A folder with the name '{new_name}' already exists in this location.")

        old_name = folder.name
        folder.name = new_name

        sync_service.log_event_for_all_affected(user.id, folder, 'updated', {'name': new_name, 'old_name': old_name})

        db.session.commit()
        return folder

    @staticmethod
    def move_folder(user, folder, new_parent):
        """Moves a folder to a new parent."""
        if not can_access(user, folder, 'move'):
            raise PermissionError("User does not have permission to move this folder.")

        if folder.is_root:
            raise ValueError("Root folder cannot be moved.")

        if not can_upload_to_folder(user, new_parent):
            raise PermissionError("User does not have permission to move folders to the destination.")

        if folder.parent_id == new_parent.id:
            return folder

        # Cycle detection: Ensure new_parent is not folder itself or a descendant
        curr_parent_id = new_parent.id
        while curr_parent_id:
            if curr_parent_id == folder.id:
                raise ValueError("Cannot move a folder into itself or one of its descendants.")

            curr = db.session.get(Folder, curr_parent_id)
            if curr:
                curr_parent_id = curr.parent_id
            else:
                break

        # Prevent duplicate sibling folder names
        existing = Folder.query.filter_by(
            parent_id=new_parent.id,
            name=folder.name,
            is_deleted=False
        ).first()
        if existing:
            raise ValueError(f"A folder with the name '{folder.name}' already exists in the destination.")

        old_parent_id = folder.parent_id
        old_parent_uuid = folder.parent.uuid if folder.parent else None

        folder.parent_id = new_parent.id

        sync_service.log_event_for_all_affected(user.id, folder, 'moved', {
            'old_parent_uuid': old_parent_uuid,
            'new_parent_uuid': new_parent.uuid
        })

        activity_log_service.log_activity(user.id, 'move_folder', 'folder', folder.id, {
            'old_parent_id': old_parent_id,
            'new_parent_id': new_parent.id
        })

        db.session.commit()
        return folder

    @staticmethod
    def copy_folder(user, folder, target_parent):
        """Copies a folder and all its contents to a target parent."""
        if not can_access(user, folder, 'view'):
            raise PermissionError("User does not have permission to access this folder.")

        if not can_upload_to_folder(user, target_parent):
            raise PermissionError("User does not have permission to copy folders to the target.")

        # Handle name duplication
        base_name = folder.name
        name = base_name
        counter = 1
        while True:
            existing = Folder.query.filter_by(
                parent_id=target_parent.id,
                name=name,
                is_deleted=False
            ).first()
            if not existing:
                break
            name = f"{base_name} (Copy {counter})"
            counter += 1

        new_folder = Folder(
            name=name,
            owner_id=user.id,
            parent_id=target_parent.id,
            is_root=False
        )
        db.session.add(new_folder)
        db.session.flush()

        sync_service.log_event_for_all_affected(user.id, new_folder, 'created', {
            'name': name,
            'parent_id': new_folder.parent_id,
            'copied_from_uuid': folder.uuid
        })

        activity_log_service.log_activity(user.id, 'copy_folder', 'folder', new_folder.id, {
            'source_folder_id': folder.id,
            'target_parent_id': target_parent.id
        })

        # Recursively copy subfolders
        for child in folder.children:
            if not child.is_deleted:
                FolderService.copy_folder(user, child, new_folder)

        # Copy files
        from app.services.file_service import file_service
        for file in folder.files:
            if not file.is_deleted:
                file_service.copy_file(user, file, new_folder)

        db.session.commit()
        return new_folder

    @staticmethod
    def list_folder_contents_paginated(user, folder, page=1, per_page=50, sort_by='name', order='asc', iso_dates=True):
        """Lists folders and files in a unified, paginated way using DB-level UNION."""
        # Define subfolders query
        q_folders = db.session.query(
            Folder.uuid.label('uuid'),
            Folder.name.label('name'),
            literal('folder').label('type'),
            Folder.updated_at.label('updated_at'),
            Folder.created_at.label('created_at'),
            literal(0).label('size'),
            User.username.label('owner_username'),
            Folder.id.label('id'),
            literal('inode/directory').label('mime_type'),
            literal('clean').label('scan_status'),
            literal(False).label('is_encrypted'),
            literal('ready').label('thumbnail_status') # Dummy for union
        ).join(User, Folder.owner_id == User.id).filter(Folder.parent_id == folder.id, Folder.is_deleted == False)

        # Define files query
        q_files = db.session.query(
            File.uuid.label('uuid'),
            File.original_filename.label('name'),
            literal('file').label('type'),
            File.updated_at.label('updated_at'),
            File.created_at.label('created_at'),
            File.size_bytes.label('size'),
            User.username.label('owner_username'),
            File.id.label('id'),
            File.mime_type.label('mime_type'),
            File.scan_status.label('scan_status'),
            File.is_encrypted.label('is_encrypted'),
            db.func.json_extract(File.preview_metadata, '$.thumbnail_status').label('thumbnail_status')
        ).join(User, File.owner_id == User.id).filter(File.folder_id == folder.id, File.is_deleted == False)

        union_stmt = q_folders.union_all(q_files)

        # Mapping sort_by to column names in the union
        sort_col = 'name'
        if sort_by == 'date':
            sort_col = 'updated_at'
        elif sort_by == 'size':
            sort_col = 'size'

        if order not in ['asc', 'desc']:
            order = 'asc'

        order_stmt = text(f"{sort_col} {order}")

        total = union_stmt.count()
        items_query = union_stmt.order_by(order_stmt).offset((page - 1) * per_page).limit(per_page)

        results = items_query.all()

        final_items = []
        for res in results:
            created_at = res.created_at
            updated_at = res.updated_at
            if iso_dates:
                created_at = res.created_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                updated_at = res.updated_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')

            item = {
                "uuid": res.uuid,
                "type": res.type,
                "name": res.name,
                "size": res.size,
                "mime_type": res.mime_type,
                "scan_status": res.scan_status,
                "parent_uuid": folder.uuid,
                "created_at": created_at,
                "updated_at": updated_at,
                "owner": res.owner_username,
                "is_encrypted": res.is_encrypted,
                "server_modified_at": updated_at
            }

            # Fetch object for permission check
            if res.type == 'folder':
                obj = db.session.get(Folder, res.id)
            else:
                obj = db.session.get(File, res.id)
                item["download_url"] = url_for("api_v1.download_file", file_uuid=res.uuid, _external=True)
                item["previewable"] = preview_service.is_previewable(obj)
                item["preview_type"] = preview_service.get_preview_type(obj)

                if item["previewable"]:
                    if item["preview_type"] == 'office_pdf':
                        item["preview_url"] = url_for("api_v1.api_get_office_preview", file_uuid=res.uuid, _external=True)
                    else:
                        item["preview_url"] = url_for("api_v1.api_preview_file", file_uuid=res.uuid, _external=True)

                # Preview Status
                metadata = obj.preview_metadata or {}
                if 'office_preview_status' in metadata:
                    item["preview_status"] = metadata.get('office_preview_status')
                elif item["preview_type"] in ['image', 'pdf', 'video', 'audio', 'text', 'csv']:
                    # For images/videos/pdfs, preview_status is ready if thumbnail_status is ready
                    if item["preview_type"] in ['image', 'video', 'pdf']:
                        item["preview_status"] = metadata.get('thumbnail_status', 'pending')
                    else:
                        item["preview_status"] = 'ready'
                else:
                    item["preview_status"] = 'none'

                item["preview_error"] = metadata.get('office_preview_error')

                # Thumbnails
                metadata = obj.preview_metadata or {}
                item["thumbnail_status"] = metadata.get('thumbnail_status', 'none')
                if item["thumbnail_status"] == 'ready':
                    item["thumbnail_small_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=res.uuid, size='small', _external=True)
                    item["thumbnail_large_url"] = url_for("api_v1.api_get_thumbnail", file_uuid=res.uuid, size='large', _external=True)

            item["permission"] = get_effective_permission(user, obj)
            item["is_starred"] = obj.is_starred

            if res.type == 'file':
                item["etag"] = obj.sha256_hash
                item["deleted_at"] = obj.deleted_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if obj.deleted_at else None
                item["sync_state"] = "synced" if not obj.is_deleted else "deleted"
                item["capabilities"] = {
                    "can_preview": item.get("previewable", False) and not obj.is_encrypted,
                    "can_download": True,
                    "can_share": not obj.is_encrypted,
                    "requires_password": obj.is_encrypted
                }
            else:
                item["deleted_at"] = obj.deleted_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if obj.deleted_at else None
                item["sync_state"] = "synced" if not obj.is_deleted else "deleted"
                item["capabilities"] = {
                    "can_preview": False,
                    "can_download": False,
                    "can_share": True,
                    "requires_password": False
                }

            final_items.append(item)

        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {
            "items": final_items,
            "pagination": {
                "total": total,
                "pages": pages,
                "current_page": page,
                "per_page": per_page,
                "has_next": page < pages,
                "has_prev": page > 1
            }
        }

    @staticmethod
    def get_recursive_stats(folder, user=None):
        """Calculates total size and file count recursively for a folder, respecting permissions."""
        total_size = 0
        total_files = 0

        # Subfolders
        for child in folder.children:
            if not child.is_deleted:
                if user and not can_access(user, child, 'view'):
                    continue
                c_size, c_files = FolderService.get_recursive_stats(child, user)
                total_size += c_size
                total_files += c_files

        # Files in this folder
        for file in folder.files:
            if not file.is_deleted:
                if user and not can_access(user, file, 'view'):
                    continue
                total_size += file.size_bytes
                total_files += 1

        return total_size, total_files

    @staticmethod
    def get_path(folder):
        """Retrieves the ancestry path of a folder."""
        path = []
        curr = folder
        while curr:
            path.append({
                "uuid": curr.uuid,
                "name": curr.name,
                "is_root": curr.is_root
            })
            if curr.parent_id:
                curr = db.session.get(Folder, curr.parent_id)
            else:
                curr = None

        return list(reversed(path))

    @staticmethod
    def search_folders(user, query=None, owner_username=None, is_starred=None, date_from=None, date_to=None, page=None, per_page=50):
        """Searches for folders based on various criteria."""
        filters = [Folder.is_deleted == False]

        if query:
            filters.append(Folder.name.ilike(f"%{query}%"))

        if is_starred is not None:
            filters.append(Folder.is_starred == is_starred)

        if date_from:
            filters.append(Folder.created_at >= date_from)
        if date_to:
            filters.append(Folder.created_at <= date_to)

        # Base query for folders owned by user
        owned_query = Folder.query.filter(Folder.owner_id == user.id, *filters)

        # Folders shared with user (including inherited)
        from app.sharing.services import sharing_service
        shared_resources = sharing_service.list_shared_with_user(user)

        shared_folder_ids = [r['resource'].id for r in shared_resources if r['resource_type'] == 'folder']

        # Subfolders in shared folders (inherited)
        inherited_folder_ids = []
        if shared_folder_ids:
            for fid in shared_folder_ids:
                inherited_folder_ids.extend(FolderService._get_all_descendant_ids(fid))

        all_accessible_folder_ids = set(shared_folder_ids) | set(inherited_folder_ids)
        shared_query = Folder.query.filter(Folder.id.in_(all_accessible_folder_ids), *filters)

        all_folders = owned_query.union(shared_query).all()

        if owner_username:
            all_folders = [f for f in all_folders if f.owner.username.lower() == owner_username.lower()]

        # Pagination
        if page:
            start = (page - 1) * per_page
            end = start + per_page
            return all_folders[start:end]

        return all_folders

    @staticmethod
    def toggle_star(user, folder):
        """Toggles the starred status of a folder."""
        if not can_access(user, folder, 'view'):
            raise PermissionError("User does not have permission to access this folder.")

        folder.is_starred = not folder.is_starred
        db.session.commit()
        return folder.is_starred

    @staticmethod
    def get_unique_folder_name(user, parent_folder, base_name):
        """
        Finds a unique folder name in the given parent folder,
        using 'Name (1)', 'Name (2)' if 'Name' already exists.
        """
        name = base_name
        counter = 1
        while True:
            # Check for existing folder in parent regardless of owner (for shared folders)
            existing = Folder.query.filter_by(
                parent_id=parent_folder.id if parent_folder else None,
                name=name,
                is_deleted=False
            ).first()
            if not existing:
                break
            name = f"{base_name} ({counter})"
            counter += 1
        return name

    @staticmethod
    def _get_all_descendant_ids(folder_id):
        """Iteratively finds all descendant folder IDs."""
        descendant_ids = []
        stack = [folder_id]
        while stack:
            curr_id = stack.pop()
            children = db.session.query(Folder.id).filter(Folder.parent_id == curr_id).all()
            child_ids = [c[0] for c in children]
            descendant_ids.extend(child_ids)
            stack.extend(child_ids)
        return descendant_ids

    @staticmethod
    def delete_folder(user, folder_uuid, permanent=False):
        """Deletes a folder, either soft or permanent."""
        if permanent:
            folder = FolderService.get_deleted_folder_by_uuid(folder_uuid, user)
            if not folder:
                raise ValueError("Folder not found in trash")
            FolderService.permanent_delete_folder(user, folder)
        else:
            folder = FolderService.get_folder_by_uuid(folder_uuid, user=user, action='delete')
            if not folder:
                raise ValueError("Folder not found")
            if folder.is_root:
                raise ValueError("Cannot delete root folder")
            FolderService.soft_delete_folder(user, folder)

    @staticmethod
    def soft_delete_folder(user, folder):
        """Soft-deletes a folder and all its contents using batched updates."""
        if not can_delete(user, folder):
            raise PermissionError("User does not have permission to delete this folder.")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        all_folder_ids = [folder.id] + FolderService._get_all_descendant_ids(folder.id)

        # 1. Update Folders
        db.session.execute(
            update(Folder).where(Folder.id.in_(all_folder_ids)).values(is_deleted=True, deleted_at=now)
        )

        # 2. Update Files in those folders
        db.session.execute(
            update(File).where(File.folder_id.in_(all_folder_ids)).values(is_deleted=True, deleted_at=now)
        )

        # Log events (might want to optimize logging for large batches in Phase 4 too,
        # but for now let's log the top-level event)
        sync_service.log_event_for_all_affected(user.id, folder, 'deleted')
        activity_log_service.log_activity(user.id, 'delete_folder', 'folder', folder.id)

        db.session.commit()
        return folder

    @staticmethod
    def restore_folder(user, folder):
        """Restores a soft-deleted folder and all its contents using batched updates."""
        if folder.owner_id != user.id and not user.is_admin:
            raise PermissionError("Only the owner can restore a folder.")

        all_folder_ids = [folder.id] + FolderService._get_all_descendant_ids(folder.id)

        # 1. Update Folders
        db.session.execute(
            update(Folder).where(Folder.id.in_(all_folder_ids)).values(is_deleted=False, deleted_at=None)
        )

        # 2. Update Files in those folders
        db.session.execute(
            update(File).where(File.folder_id.in_(all_folder_ids)).values(is_deleted=False, deleted_at=None)
        )

        sync_service.log_event_for_all_affected(user.id, folder, 'created', {'restored': True})
        activity_log_service.log_activity(user.id, 'restore_folder', 'folder', folder.id)

        db.session.commit()
        return folder

    @staticmethod
    def permanent_delete_folder(user, folder):
        """Permanently deletes a folder and all its contents using iterative approach."""
        if folder.owner_id != user.id and not user.is_admin:
            raise PermissionError("Only the owner can permanently delete a folder.")

        # For permanent deletion, we still need to delete files from storage
        # so we iterate through them.
        all_folder_ids = [folder.id] + FolderService._get_all_descendant_ids(folder.id)

        from app.models.file import File
        from app.services.file_service import file_service

        # 1. Delete all files in these folders from storage and DB
        files = File.query.filter(File.folder_id.in_(all_folder_ids)).all()
        for f in files:
            file_service.permanent_delete_file(user, f)

        # 2. Delete folders from DB (bottom-up to satisfy FKs if they weren't CASCADE)
        # Actually, SQL order matters if there are FKs.
        # But Folder model parent_id is nullable.
        # Let's delete in reverse order of discovery.
        for f_id in reversed(all_folder_ids):
            f_obj = db.session.get(Folder, f_id)
            if f_obj:
                db.session.delete(f_obj)

        activity_log_service.log_activity(user.id, 'permanent_delete_folder', 'folder', folder.id)
        db.session.commit()

    @staticmethod
    def empty_trash(user):
        """Permanently deletes all items in the trash for a user."""
        # Find all root-level deleted items (either root-level folders or root-level files or items whose parents are not deleted)
        # Actually, just find everything marked is_deleted=True and owner_id=user.id
        # To avoid double deletion, we can find folders that are deleted but whose parents are NOT deleted (or are root)

        deleted_folders = Folder.query.filter_by(owner_id=user.id, is_deleted=True).all()
        # We need to be careful with recursion. Permanent_delete_folder handles recursion.
        # We only need to call it on "top-level" deleted folders to be efficient.
        for folder in deleted_folders:
            # If parent is None or parent is not deleted, it's a top-level deleted folder
            if not folder.parent_id or not folder.parent.is_deleted:
                FolderService.permanent_delete_folder(user, folder)

        from app.models.file import File
        from app.services.file_service import file_service
        deleted_files = File.query.filter_by(owner_id=user.id, is_deleted=True).all()
        for file in deleted_files:
            if not file.folder_id or not file.folder.is_deleted:
                file_service.permanent_delete_file(user, file)

        db.session.commit()

folder_service = FolderService()
