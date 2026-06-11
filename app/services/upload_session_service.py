"""
Description: Service layer implementation for UploadSessionService.
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
import tempfile
import hashlib
import re
from datetime import datetime, timezone, timedelta
from flask import current_app
from app.extensions import db
from app.models.upload_session import UploadSession
from app.models.folder import Folder
from app.models.file import File
from app.services.folder_service import folder_service
from app.services.upload_service import upload_service
from app.services.upload_policy_service import upload_policy_service

class UploadSessionService:
    MAX_CHUNK_SIZE = 10 * 1024 * 1024 # 10MB limit per chunk

    @staticmethod
    def create_session(user, filename, total_size, total_chunks, sha256_hash, folder_uuid=None, relative_path=None):
        """Initializes a new resumable upload session."""
        if not filename:
            raise ValueError("Filename is required")
        extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        upload_policy_service.validate_extension(extension)
        if not isinstance(total_size, int) or total_size < 0:
            raise ValueError("Total size must be a non-negative integer")
        if not isinstance(total_chunks, int) or total_chunks <= 0:
            raise ValueError("Total chunks must be a positive integer")
        if not sha256_hash:
            raise ValueError("SHA256 hash is required for resumable uploads")

        # Validate SHA256 format (64-char hex)
        if not re.fullmatch(r"^[a-fA-F0-9]{64}$", sha256_hash):
            raise ValueError("Invalid SHA256 hash format")

        try:
            # Check for existing active session for this user and hash to enable resume
            existing_session = UploadSession.query.filter_by(
                user_id=user.id,
                sha256_hash=sha256_hash,
                status='active'
            ).first()

            if existing_session:
                # Update expiration
                existing_session.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)
                db.session.commit()
                return existing_session

            folder = None
            if folder_uuid:
                folder = folder_service.get_folder_by_uuid(folder_uuid, user=user, action='upload')
            else:
                folder = folder_service.get_user_root_folder(user)

            # Quota check at start
            current_usage = db.session.query(db.func.sum(File.size_bytes)).filter_by(owner_id=user.id, is_deleted=False).scalar() or 0
            if current_usage + total_size > user.storage_quota_bytes:
                raise ValueError("Storage quota exceeded")

            session = UploadSession(
                user_id=user.id,
                folder_id=folder.id if folder else None,
                filename=filename,
                total_size=total_size,
                total_chunks=total_chunks,
                sha256_hash=sha256_hash,
                relative_path=relative_path,
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)
            )
            db.session.add(session)
            db.session.commit()
            return session
        except PermissionError:
            raise
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to create upload session: {str(e)}")

    @staticmethod
    def get_session(session_uuid, user):
        """Retrieves an active session for a user."""
        return UploadSession.query.filter_by(
            uuid=session_uuid,
            user_id=user.id,
            status='active'
        ).first()

    @staticmethod
    def save_chunk(session, chunk_index, chunk_data):
        """Saves a chunk of data for a session."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if session.expires_at < now:
            session.status = 'failed'
            db.session.commit()
            raise ValueError("Upload session has expired")

        if chunk_index < 0 or chunk_index >= session.total_chunks:
            raise ValueError("Invalid chunk index")

        if not chunk_data:
            raise ValueError("No data provided")

        if len(chunk_data) > UploadSessionService.MAX_CHUNK_SIZE:
            raise ValueError(f"Chunk size exceeds maximum allowed ({UploadSessionService.MAX_CHUNK_SIZE} bytes)")

        # Store chunk in temporary location
        temp_dir = os.path.join(current_app.config["STORAGE_PATH"], "tmp_uploads", session.uuid)
        os.makedirs(temp_dir, exist_ok=True)

        chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index}")
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)

        # Update session
        completed = list(session.completed_chunks or [])
        if chunk_index not in completed:
            completed.append(chunk_index)
            session.completed_chunks = completed
            db.session.commit()

        return True

    @staticmethod
    def finalize_session(session, user):
        """Reassembles and processes the final file."""
        if len(session.completed_chunks) < session.total_chunks:
            raise ValueError("Not all chunks uploaded")

        temp_dir = os.path.join(current_app.config["STORAGE_PATH"], "tmp_uploads", session.uuid)

        # Reassemble and verify checksum
        sha256 = hashlib.sha256()
        actual_size = 0

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            try:
                for i in range(session.total_chunks):
                    chunk_path = os.path.join(temp_dir, f"chunk_{i}")
                    if not os.path.exists(chunk_path):
                        raise ValueError(f"Missing chunk {i}")
                    with open(chunk_path, "rb") as f:
                        data = f.read()
                        sha256.update(data)
                        actual_size += len(data)
                        tmp.write(data)

                tmp.flush()

                if actual_size != session.total_size:
                    raise ValueError(f"Total size mismatch: expected {session.total_size}, got {actual_size}")

                final_hash = sha256.hexdigest()
                if final_hash != session.sha256_hash:
                    raise ValueError(f"Checksum mismatch: expected {session.sha256_hash}, got {final_hash}")

                # Process as standard upload
                with open(tmp.name, "rb") as f:
                    # Named adapter for UploadService
                    class NamedFile:
                        def __init__(self, stream, filename):
                            self.stream = stream
                            self.filename = filename
                        def read(self, *args, **kwargs): return self.stream.read(*args, **kwargs)
                        def seek(self, *args, **kwargs): return self.stream.seek(*args, **kwargs)
                        def tell(self, *args, **kwargs): return self.stream.tell(*args, **kwargs)

                    file_obj = NamedFile(f, session.filename)
                    folder = db.session.get(Folder, session.folder_id) if session.folder_id else None

                    # Handle directory structure if relative_path provided
                    if session.relative_path:
                        path_parts = session.relative_path.split('/')[:-1] # Remove filename
                        for part in path_parts:
                            if part:
                                folder = upload_service._get_or_create_subfolder(user, folder, part, commit=True)

                    new_file = upload_service.process_upload(user, folder, file_obj)

                    # Cleanup
                    session.status = 'completed'
                    db.session.commit()
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)

                    return new_file
            except Exception as e:
                # Cleanup on failed finalize
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                session.status = 'failed'
                db.session.commit()
                raise e
            finally:
                if os.path.exists(tmp.name):
                    os.remove(tmp.name)

    @staticmethod
    def cleanup_expired_sessions():
        """Removes expired upload sessions and their temporary files."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_sessions = UploadSession.query.filter(
            UploadSession.expires_at < now
        ).all()

        count = 0
        for session in expired_sessions:
            temp_dir = os.path.join(current_app.config["STORAGE_PATH"], "tmp_uploads", session.uuid)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            db.session.delete(session)
            count += 1

        db.session.commit()
        return count

    @staticmethod
    def cancel_session(session_uuid, user):
        """Cancels an upload session and cleans up temporary files."""
        session = UploadSession.query.filter_by(uuid=session_uuid, user_id=user.id).first()
        if not session:
            return False

        # Cleanup temp files
        temp_dir = os.path.join(current_app.config["STORAGE_PATH"], "tmp_uploads", session_uuid)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        db.session.delete(session)
        db.session.commit()
        return True

upload_session_service = UploadSessionService()
