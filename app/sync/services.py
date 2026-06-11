"""
Description: Implements sync service logic for sync event processing.
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
from app.models.sync_event import SyncEvent
from app.models.share import Share

class SyncService:
    @staticmethod
    def log_event(user_id, resource_type, resource_id, resource_uuid, action, metadata=None):
        """Logs a sync event for a user."""
        event = SyncEvent(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_uuid=resource_uuid,
            action=action,
            metadata_json=metadata
        )
        db.session.add(event)
        return event

    @staticmethod
    def log_event_for_all_affected(actor_user_id, resource, action, metadata=None):
        """
        Logs a sync event for the actor AND all users who have access to this resource via sharing.
        'resource' must be a Folder or File model instance.
        """
        from app.models.folder import Folder
        from app.models.file import File

        res_type = 'folder' if isinstance(resource, Folder) else 'file'
        res_id = resource.id
        res_uuid = resource.uuid

        # 1. Log for the actor
        # Strip internal integer IDs from metadata
        if metadata:
            metadata = {k: v for k, v in metadata.items() if not k.endswith('_id')}

        SyncService.log_event(actor_user_id, res_type, res_id, res_uuid, action, metadata)

        # 2. Find all users who have access to this resource via direct shares
        affected_user_ids = {actor_user_id}

        direct_shares = Share.query.filter_by(resource_type=res_type, resource_id=res_id).all()
        for share in direct_shares:
            affected_user_ids.add(share.shared_with_user_id)

        # 3. Handle inheritance: find shares on ancestor folders with inherit_to_children=True
        parent_folder = None
        if res_type == 'file':
            parent_folder = resource.folder
        else:
            parent_folder = resource.parent

        ancestor = parent_folder
        while ancestor:
            ancestor_shares = Share.query.filter_by(
                resource_type='folder',
                resource_id=ancestor.id,
                inherit_to_children=True
            ).all()
            for share in ancestor_shares:
                affected_user_ids.add(share.shared_with_user_id)
            ancestor = ancestor.parent

        # 4. Log events for all unique affected users (excluding the actor if already logged)
        for user_id in affected_user_ids:
            if user_id != actor_user_id:
                SyncService.log_event(user_id, res_type, res_id, res_uuid, action, metadata)

    @staticmethod
    def get_changes(user, since_timestamp=None, cursor=None, per_page=100):
        """Retrieves sync changes for a user using timestamp or cursor."""
        query = SyncEvent.query.filter_by(user_id=user.id)

        if cursor:
            try:
                query = query.filter(SyncEvent.id > int(cursor))
            except (ValueError, TypeError):
                pass
        elif since_timestamp:
            try:
                # Handle both ISO strings and numeric timestamps
                if isinstance(since_timestamp, str):
                    since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
                else:
                    since_dt = datetime.fromtimestamp(float(since_timestamp), tz=timezone.utc)

                # Handle SQLite naive datetime
                since_dt_naive = since_dt.replace(tzinfo=None)
                query = query.filter(SyncEvent.event_time > since_dt_naive)
            except (ValueError, TypeError):
                pass

        query = query.order_by(SyncEvent.id.asc())

        # Use limit for cursor-based pagination instead of offset-based paginate()
        items = query.limit(per_page + 1).all()

        has_more = len(items) > per_page
        if has_more:
            items = items[:per_page]

        if items:
            next_cursor = str(items[-1].id)
        else:
            next_cursor = cursor # Keep previous cursor if no new items

        return {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "changes": [
                {
                    "uuid": e.uuid,
                    "resource_type": e.resource_type,
                    "resource_uuid": e.resource_uuid,
                    "action": e.action,
                    "event_time": e.event_time.isoformat() + "Z",
                    "metadata": e.metadata_json
                } for e in items
            ],
            "success": True,
            "has_more": has_more,
            "next_cursor": next_cursor
        }

sync_service = SyncService()
