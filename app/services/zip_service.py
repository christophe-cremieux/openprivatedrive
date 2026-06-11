"""
Description: Service layer implementation for ZipService.
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
import tempfile
from flask import current_app
from app.services.storage_service import storage_service
from app.drive.permissions import can_access

class ZipService:
    @staticmethod
    def create_zip_file(user, files, folders):
        """
        Creates a ZIP archive as a temporary file containing the provided files and folders.
        Ensures permission checks are respected.
        """
        temp_dir = os.path.join(current_app.config['STORAGE_PATH'], 'temp')
        os.makedirs(temp_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(temp_dir, 0o700)
        except Exception:
            pass

        tmp = tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, suffix=".zip", prefix="bulk_download_")
        tmp_path = tmp.name
        tmp.close()

        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            name_tracker = {} # Track names per directory level in ZIP

            # Add directly selected files to the root of the ZIP
            for file in files:
                if not can_access(user, file, 'download'):
                    continue
                full_path = storage_service.get_full_path(file.storage_path)
                if os.path.exists(full_path) and not file.is_encrypted:
                    arcname = ZipService._get_unique_arcname(file.original_filename, "", name_tracker)
                    zf.write(full_path, arcname)

            # Add folders recursively
            for folder in folders:
                if not can_access(user, folder, 'view'):
                    continue
                # For folders, we also want unique names at the root level
                folder_arcname = ZipService._get_unique_arcname(folder.name, "", name_tracker)
                ZipService._add_folder_to_zip(user, zf, folder, folder_arcname)

        return tmp_path

    @staticmethod
    def _get_unique_arcname(filename, directory, name_tracker):
        """Generates a unique archive path by adding suffixes if name collisions occur."""
        full_dir = directory
        if full_dir not in name_tracker:
            name_tracker[full_dir] = set()

        base_name = filename
        ext = ""
        if "." in filename:
            parts = filename.rsplit(".", 1)
            base_name, ext = parts[0], "." + parts[1]

        candidate = filename
        counter = 1
        while candidate in name_tracker[full_dir]:
            candidate = f"{base_name}_{counter}{ext}"
            counter += 1

        name_tracker[full_dir].add(candidate)
        return os.path.join(directory, candidate) if directory else candidate

    @staticmethod
    def _add_folder_to_zip(user, zf, folder, zip_path):
        """Recursively adds folder contents to the ZIP archive."""
        # Note: name_tracker is local to this scope or passed along.
        # Since folders are usually unique within their parent in the app,
        # but we might be merging folders from different parents.
        # Let's pass a fresh name tracker for EACH recursive level.
        sub_name_tracker = {}

        # Add subfolders
        for child in folder.children:
            if not child.is_deleted and can_access(user, child, 'view'):
                child_arcname = ZipService._get_unique_arcname(child.name, zip_path, sub_name_tracker)
                ZipService._add_folder_to_zip(user, zf, child, child_arcname)

        # Add files in this folder
        for file in folder.files:
            if not file.is_deleted and not file.is_encrypted and can_access(user, file, 'download'):
                full_path = storage_service.get_full_path(file.storage_path)
                if os.path.exists(full_path):
                    file_arcname = ZipService._get_unique_arcname(file.original_filename, zip_path, sub_name_tracker)
                    zf.write(full_path, file_arcname)

    @staticmethod
    def get_recursive_items_stats(user, files, folders):
        """Calculates total size and file count for a set of files and folders, respecting permissions."""
        total_size = 0
        total_files = 0
        skipped_encrypted = 0
        skipped_quarantined = 0
        skipped_missing = 0

        from app.services.folder_service import folder_service

        for f in files:
            # For direct selection, if it's quarantined, it's a visible skip reason even if view permission is False for non-admins
            if f.is_quarantined:
                skipped_quarantined += 1
                continue

            if not can_access(user, f, 'view'): # Check basic access
                continue
            if f.is_encrypted:
                skipped_encrypted += 1
                continue
            if not os.path.exists(storage_service.get_full_path(f.storage_path)):
                skipped_missing += 1
                continue

            total_size += f.size_bytes
            total_files += 1

        for f in folders:
            if can_access(user, f, 'view'):
                # We need a more detailed recursive stat that also tracks skipped items
                s, count, enc, quar, miss = ZipService._get_recursive_stats_with_skipped(f, user)
                total_size += s
                total_files += count
                skipped_encrypted += enc
                skipped_quarantined += quar
                skipped_missing += miss

        return {
            'total_size': total_size,
            'total_files': total_files,
            'skipped_encrypted': skipped_encrypted,
            'skipped_quarantined': skipped_quarantined,
            'skipped_missing': skipped_missing
        }

    @staticmethod
    def _get_recursive_stats_with_skipped(folder, user):
        """Recursive helper to get stats and skipped counts."""
        total_size = 0
        total_files = 0
        skipped_encrypted = 0
        skipped_quarantined = 0
        skipped_missing = 0

        for child in folder.children:
            if not child.is_deleted and can_access(user, child, 'view'):
                s, count, enc, quar, miss = ZipService._get_recursive_stats_with_skipped(child, user)
                total_size += s
                total_files += count
                skipped_encrypted += enc
                skipped_quarantined += quar
                skipped_missing += miss

        for file in folder.files:
            if not file.is_deleted:
                # Quarantined is skipped even if view is False
                if file.is_quarantined:
                    skipped_quarantined += 1
                    continue

                if not can_access(user, file, 'view'):
                    continue
                if file.is_encrypted:
                    skipped_encrypted += 1
                    continue
                if not os.path.exists(storage_service.get_full_path(file.storage_path)):
                    skipped_missing += 1
                    continue

                total_size += file.size_bytes
                total_files += 1

        return total_size, total_files, skipped_encrypted, skipped_quarantined, skipped_missing

zip_service = ZipService()
