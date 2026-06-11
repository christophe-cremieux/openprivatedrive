"""
Description: Service layer implementation for StorageBackend.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
import uuid
from flask import current_app
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    @abstractmethod
    def save(self, file_uuid, file_data):
        pass

    @abstractmethod
    def delete(self, rel_path):
        pass

    @abstractmethod
    def copy(self, src_rel_path, dest_file_uuid):
        pass

    @abstractmethod
    def get_full_path(self, rel_path):
        pass

class LocalStorageBackend(StorageBackend):
    def __init__(self, base_path):
        self.base_path = base_path

    def generate_storage_path(self, file_uuid):
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("files", shard1, shard2, f"{file_uuid}.bin")

    def generate_thumbnail_path(self, file_uuid, size):
        """Generates a relative path for a thumbnail."""
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("thumbnails", shard1, shard2, f"{file_uuid}-{size}.webp")

    def generate_preview_path(self, file_uuid):
        """Generates a relative path for a generated PDF preview."""
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("previews", shard1, shard2, f"{file_uuid}.pdf")

    def ensure_directory_exists(self, full_path):
        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def save(self, file_uuid, file_data):
        rel_path = self.generate_storage_path(file_uuid)
        full_path = self.get_full_path(rel_path)
        self.ensure_directory_exists(full_path)

        with open(full_path, "wb") as f:
            if isinstance(file_data, bytes):
                f.write(file_data)
            else:
                chunk_size = 4096
                while True:
                    chunk = file_data.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
        return rel_path

    def delete(self, rel_path):
        full_path = self.get_full_path(rel_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    def copy(self, src_rel_path, dest_file_uuid):
        import shutil
        dest_rel_path = self.generate_storage_path(dest_file_uuid)
        src_full_path = self.get_full_path(src_rel_path)
        dest_full_path = self.get_full_path(dest_rel_path)

        self.ensure_directory_exists(dest_full_path)
        shutil.copy2(src_full_path, dest_full_path)
        return dest_rel_path

    def get_full_path(self, rel_path):
        return os.path.join(self.base_path, rel_path)

class StorageService:
    def __init__(self):
        self._backend_cache = {}

    @property
    def backend(self):
        # Use current_app and STORAGE_PATH as key to avoid global caching across different apps
        # and to respect STORAGE_PATH changes in tests.
        app_obj = current_app._get_current_object()
        app_id = id(app_obj)
        storage_path = app_obj.config.get("STORAGE_PATH")

        cache_key = (app_id, storage_path)
        if cache_key not in self._backend_cache:
            self._backend_cache[cache_key] = LocalStorageBackend(storage_path)
        return self._backend_cache[cache_key]

    def get_full_path(self, rel_path):
        return self.backend.get_full_path(rel_path)

    def save_file(self, file_uuid, file_data):
        return self.backend.save(file_uuid, file_data)

    def delete_file(self, rel_path):
        return self.backend.delete(rel_path)

    def generate_storage_path(self, file_uuid):
        # Delegate to backend if it has it, or handle it for backward compatibility in tests
        if hasattr(self.backend, 'generate_storage_path'):
            return self.backend.generate_storage_path(file_uuid)
        # Fallback
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("files", shard1, shard2, f"{file_uuid}.bin")

    def generate_thumbnail_path(self, file_uuid, size):
        if hasattr(self.backend, 'generate_thumbnail_path'):
            return self.backend.generate_thumbnail_path(file_uuid, size)
        # Fallback
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("thumbnails", shard1, shard2, f"{file_uuid}-{size}.webp")

    def generate_preview_path(self, file_uuid):
        if hasattr(self.backend, 'generate_preview_path'):
            return self.backend.generate_preview_path(file_uuid)
        # Fallback
        file_uuid = str(file_uuid)
        shard1 = file_uuid[0:2]
        shard2 = file_uuid[2:4]
        return os.path.join("previews", shard1, shard2, f"{file_uuid}.pdf")

    def is_safe_path(self, rel_path):
        """Validates that a relative path is safely contained within the storage root."""
        if not rel_path:
            return False

        try:
            full_path = self.get_full_path(rel_path)
            storage_root = os.path.abspath(current_app.config["STORAGE_PATH"])
            abs_file_path = os.path.abspath(full_path)
            return os.path.commonpath([storage_root, abs_file_path]) == storage_root
        except Exception:
            return False

storage_service = StorageService()
