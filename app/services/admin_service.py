"""
Description: Service layer implementation for AdminService.
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
from flask import current_app
from app.extensions import db
from app.models.user import User
from app.models.file import File
from app.models.folder import Folder
from app.models.share import Share
from app.models.public_link import PublicLink
from app.models.activity_log import ActivityLog
from app.models.api_token import ApiToken
from app.models.sync_event import SyncEvent
from app.models.upload_session import UploadSession
from app.models.system_stat import SystemStat
from app.models.zip_extract_job import ZipExtractJob
from app.models.password_reset_token import PasswordResetToken

class AdminService:
    @staticmethod
    def perform_system_reset(admin_user, mode='data_only'):
        """
        Performs a factory reset of the system.
        'data_only': Deletes all files, folders, shares, and metadata, but keeps user accounts.
        'full': Deletes everything including user accounts (except the current admin).
        """
        try:
            # 1. Delete Database Records
            # Order matters to respect potential (though not always enforced in SQLite) FKs

            # Metadata and events
            SyncEvent.query.delete()
            ActivityLog.query.delete()
            ApiToken.query.delete()
            UploadSession.query.delete()
            ZipExtractJob.query.delete()
            PasswordResetToken.query.delete()

            # Sharing
            PublicLink.query.delete()
            Share.query.delete()

            # Content
            File.query.delete()
            # Root folders might have parent_id=None, but subfolders have parent_id
            # To avoid FK issues in some DBs, we might need to nullify parent_ids first
            # or delete in specific order. SQLite with FK ON needs careful ordering.
            db.session.query(Folder).update({Folder.parent_id: None})
            db.session.flush()

            Folder.query.delete()

            # System Stats (optional, but good for a "clean" reset)
            SystemStat.query.delete()

            if mode == 'full':
                # Delete all users EXCEPT the admin performing the reset
                User.query.filter(User.id != admin_user.id).delete()

            db.session.commit()

            # 2. Purge Physical Storage
            storage_path = current_app.config.get('STORAGE_PATH')
            if storage_path and os.path.exists(storage_path):
                # We want to clear the contents of storage_path but keep the directory itself
                for item in os.listdir(storage_path):
                    item_path = os.path.join(storage_path, item)
                    try:
                        if os.path.isfile(item_path) or os.path.islink(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except Exception as e:
                        current_app.logger.error(f"Failed to delete {item_path}: {e}")

                # Re-create expected subdirectories
                os.makedirs(os.path.join(storage_path, 'files'), exist_ok=True)
                os.makedirs(os.path.join(storage_path, 'thumbnails'), exist_ok=True)
                os.makedirs(os.path.join(storage_path, 'previews'), exist_ok=True)
                os.makedirs(os.path.join(storage_path, 'temp'), exist_ok=True)
                os.makedirs(os.path.join(storage_path, 'chunks'), exist_ok=True)

            return True, "System reset completed successfully."
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Factory Reset Failed: {str(e)}")
            return False, f"Factory reset failed: {str(e)}"

admin_service = AdminService()
