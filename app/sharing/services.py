"""
Description: Handles sharing service operations and share management logic.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

from datetime import datetime, timezone
from app.extensions import db
from app.models.share import Share
from app.models.user import User
from app.models.folder import Folder
from app.models.file import File
from app.drive.permissions import can_access, OWNER, MANAGER
from app.sync.services import sync_service
from app.services.activity_log_service import activity_log_service

class SharingService:
    @staticmethod
    def share_resource(shared_by, resource, share_with_username, permission, inherit=True, expires_at=None):
        """Shares a resource with another user."""
        if not can_access(shared_by, resource, 'share'):
            raise ValueError("User does not have permission to share this resource.")

        target_user = User.query.filter_by(username=share_with_username).first()
        if not target_user:
            raise ValueError(f"User '{share_with_username}' not found.")

        if target_user.id == shared_by.id:
            raise ValueError("You cannot share a resource with yourself.")

        res_type = 'folder' if isinstance(resource, Folder) else 'file'

        # Check if already shared
        existing_share = Share.query.filter_by(
            resource_type=res_type,
            resource_id=resource.id,
            shared_with_user_id=target_user.id
        ).first()

        if existing_share:
            existing_share.permission = permission
            existing_share.inherit_to_children = inherit
            existing_share.expires_at = expires_at
            share = existing_share
            action = 'updated'
        else:
            share = Share(
                resource_type=res_type,
                resource_id=resource.id,
                shared_by_user_id=shared_by.id,
                shared_with_user_id=target_user.id,
                permission=permission,
                inherit_to_children=inherit,
                expires_at=expires_at
            )
            db.session.add(share)
            action = 'shared'

        db.session.flush()
        sync_service.log_event(target_user.id, res_type, resource.id, resource.uuid, action, {'shared_by': shared_by.username, 'permission': permission})
        activity_log_service.log_activity(shared_by.id, f'share_{res_type}', res_type, resource.id)

        db.session.commit()
        return share

    @staticmethod
    def get_share_by_uuid(share_uuid, user=None):
        """Retrieves a share record by its UUID and optionally checks access."""
        share = Share.query.filter_by(uuid=share_uuid).first()
        if not share:
            return None

        if user:
            # Re-implementing access check logic from remove_share
            resource = None
            if share.resource_type == 'folder':
                resource = db.session.get(Folder, share.resource_id)
            else:
                resource = db.session.get(File, share.resource_id)

            if resource:
                # If resource exists, check if user can share or if they are the recipient
                if not can_access(user, resource, 'share') and user.id != share.shared_with_user_id:
                    raise PermissionError("User does not have permission to access this share.")
            else:
                # If resource is gone, only allow recipient or creator?
                # For now let's keep it simple.
                pass

        return share

    @staticmethod
    def remove_share(user, share_uuid):
        """Removes a share record."""
        share = SharingService.get_share_by_uuid(share_uuid, user=user)
        if not share:
            raise ValueError("Share record not found.")

        resource = None
        if share.resource_type == 'folder':
            resource = db.session.get(Folder, share.resource_id)
        else:
            resource = db.session.get(File, share.resource_id)

        if not resource:
            # Resource gone? Just delete the share.
            db.session.delete(share)
            db.session.commit()
            return

        sync_service.log_event(share.shared_with_user_id, share.resource_type, share.resource_id, resource.uuid, 'unshared', {'removed_by': user.username})

        db.session.delete(share)
        db.session.commit()

    @staticmethod
    def list_shared_with_user(user):
        """Lists all resources shared with a user."""
        shares = Share.query.filter_by(shared_with_user_id=user.id).filter(
            (Share.expires_at == None) | (Share.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))
        ).all()

        results = []
        for share in shares:
            resource = None
            if share.resource_type == 'folder':
                resource = db.session.get(Folder, share.resource_id)
            else:
                resource = db.session.get(File, share.resource_id)

            if resource and not resource.is_deleted:
                results.append({
                    'share_uuid': share.uuid,
                    'resource': resource,
                    'resource_type': share.resource_type,
                    'permission': share.permission,
                    'shared_by': share.shared_by.username
                })
        return results

    @staticmethod
    def update_share_permission(user, share_uuid, permission):
        """Updates the permission level for a specific share."""
        share = SharingService.get_share_by_uuid(share_uuid, user=user)
        if not share:
            raise ValueError("Share not found")

        resource = None
        if share.resource_type == 'folder':
            resource = db.session.get(Folder, share.resource_id)
        else:
            resource = db.session.get(File, share.resource_id)

        if not can_access(user, resource, 'share'):
            raise PermissionError("User does not have permission to update shares for this resource.")

        share.permission = permission
        db.session.commit()
        return share

    @staticmethod
    def list_resource_shares(user, resource):
        """Lists all users a resource is shared with, including inherited ones."""
        if not can_access(user, resource, 'view'):
            raise ValueError("User does not have permission to view shares for this resource.")

        res_type = 'folder' if isinstance(resource, Folder) else 'file'

        # 1. Direct shares
        direct_shares = Share.query.filter_by(resource_type=res_type, resource_id=resource.id).all()

        results = []
        for s in direct_shares:
            results.append({
                'uuid': s.uuid,
                'username': s.shared_with.username,
                'permission': s.permission,
                'is_inherited': False,
                'inherited_from': None
            })

        # 2. Inherited shares
        parent = None
        if res_type == 'file':
            parent = resource.folder
        else:
            parent = resource.parent

        while parent:
            parent_shares = Share.query.filter_by(resource_type='folder', resource_id=parent.id, inherit_to_children=True).all()
            for s in parent_shares:
                # Check if this user already has a direct or more specific share
                if not any(r['username'] == s.shared_with.username for r in results):
                    results.append({
                        'uuid': s.uuid,
                        'username': s.shared_with.username,
                        'permission': s.permission,
                        'is_inherited': True,
                        'inherited_from': {'uuid': parent.uuid, 'name': parent.name}
                    })
            parent = parent.parent

        return results

sharing_service = SharingService()
