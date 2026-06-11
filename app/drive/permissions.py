"""
Description: Contains drive-specific permission helpers and access control checks.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

# app/drive/permissions.py

from datetime import datetime, timezone
from app.models.folder import Folder
from app.models.file import File
from app.models.share import Share

# Permission Levels
OWNER = "owner"
MANAGER = "manager"
EDITOR = "editor"
VIEWER = "viewer"
NONE = None

PERMISSION_ORDER = [NONE, VIEWER, EDITOR, MANAGER, OWNER]

def get_effective_permission(user, resource):
    """
    Determines the effective permission level a user has on a resource.
    Checks ownership, direct shares, and inherited folder shares.
    """
    if not user or not resource:
        return NONE

    if user.is_admin:
        return OWNER

    if resource.owner_id == user.id:
        return OWNER

    # Determine resource type and ID
    res_type = 'folder' if isinstance(resource, Folder) else 'file'
    res_id = resource.id

    # Check direct shares
    share = Share.query.filter_by(
        resource_type=res_type,
        resource_id=res_id,
        shared_with_user_id=user.id
    ).filter(
        (Share.expires_at == None) | (Share.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))
    ).first()

    effective_perm = share.permission if share else NONE

    # If it's a file, check parent folder shares if not already a manager
    if res_type == 'file' and effective_perm != MANAGER:
        if resource.folder_id:
            parent_perm = get_effective_permission(user, resource.folder)
            if PERMISSION_ORDER.index(parent_perm) > PERMISSION_ORDER.index(effective_perm):
                effective_perm = parent_perm

    # If it's a folder, check parent folder shares recursively
    elif res_type == 'folder' and effective_perm != MANAGER:
        if resource.parent_id:
            # We only inherit if inherit_to_children is True for the share
            # But get_effective_permission logic needs to know if the permission was inherited.
            # Let's simplify: check all ancestors for a share with inherit_to_children=True
            ancestor = resource.parent
            while ancestor:
                a_share = Share.query.filter_by(
                    resource_type='folder',
                    resource_id=ancestor.id,
                    shared_with_user_id=user.id,
                    inherit_to_children=True
                ).filter(
                    (Share.expires_at == None) | (Share.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))
                ).first()

                if a_share:
                    if PERMISSION_ORDER.index(a_share.permission) > PERMISSION_ORDER.index(effective_perm):
                        effective_perm = a_share.permission
                    if effective_perm == MANAGER:
                        break
                ancestor = ancestor.parent

    return effective_perm

def can_access(user, resource, action):
    """
    Checks if a user can perform a specific action on a resource.
    Actions: view, download, upload, rename, move, delete, share, manage
    """
    if not user or not resource:
        return False

    # Deleted resources are inaccessible except special trash flows (handled elsewhere)
    if resource.is_deleted:
        return False

    # Prevent access to quarantined files
    if isinstance(resource, File) and resource.is_quarantined and not user.is_admin:
        # Only admin can see/manage quarantined files
        return False

    perm = get_effective_permission(user, resource)

    if perm == OWNER:
        return True

    is_allowed = False

    if action in ['view', 'download']:
        is_allowed = perm in [VIEWER, EDITOR, MANAGER]

    elif action in ['upload', 'rename']:
        is_allowed = perm in [EDITOR, MANAGER]

    elif action in ['delete', 'share', 'move']:
        is_allowed = perm == MANAGER

    elif action == 'manage':
        is_allowed = perm == OWNER

    if not is_allowed:
        # Only log if user and resource are real objects (not mocks from tests)
        if hasattr(user, 'id') and hasattr(resource, 'id'):
            from app.services.activity_log_service import activity_log_service
            res_type = 'folder' if isinstance(resource, Folder) else 'file'
            activity_log_service.log_activity(user.id, 'permission_denied', res_type, resource.id, metadata={'action': action})

    return is_allowed

def can_upload_to_folder(user, folder):
    """Checks if a user can upload files or create subfolders."""
    return can_access(user, folder, 'upload')

def can_share(user, resource):
    """Checks if a user can share a resource."""
    return can_access(user, resource, 'share')

def can_delete(user, resource):
    """Checks if a user can delete a resource."""
    return can_access(user, resource, 'delete')
