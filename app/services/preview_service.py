"""
Description: Service layer implementation for PreviewService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
from flask import current_app
from app.models.file import File
from app.services.storage_service import storage_service

class PreviewService:
    TEXT_EXTENSIONS = {
        'txt', 'text', 'log', 'md', 'markdown', 'json', 'jsonl', 'ndjson',
        'js', 'mjs', 'cjs', 'css', 'xml', 'yaml', 'yml', 'toml', 'ini',
        'cfg', 'conf', 'env', 'csv', 'tsv', 'sql', 'sh', 'bash', 'zsh',
        'ps1', 'bat', 'cmd', 'py', 'rb', 'php', 'java', 'c', 'h', 'cpp',
        'hpp', 'cs', 'go', 'rs', 'swift', 'kt', 'kts', 'html', 'htm',
        'svg', 'vue', 'svelte', 'jsx', 'tsx', 'ts'
    }
    TEXT_MIME_TYPES = {
        'application/json',
        'application/javascript',
        'application/x-javascript',
        'application/xml',
        'application/x-yaml',
        'application/toml',
        'application/sql',
        'application/x-sh',
        'application/x-shellscript',
        'application/x-ndjson',
        'text/javascript',
        'text/markdown',
        'text/x-markdown',
        'text/xml',
        'text/yaml',
        'text/x-yaml',
        'text/html',
        'image/svg+xml',
    }

    @staticmethod
    def _get_extension(file_record: File) -> str:
        extension = getattr(file_record, 'extension', None)
        if extension:
            return extension.lower().lstrip('.')

        filename = file_record.original_filename or ''
        return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

    @classmethod
    def is_text_like(cls, file_record: File) -> bool:
        mime_type = file_record.mime_type or ''
        extension = cls._get_extension(file_record)

        return (
            mime_type.startswith('text/') or
            mime_type in cls.TEXT_MIME_TYPES or
            extension in cls.TEXT_EXTENSIONS
        )

    @staticmethod
    def get_preview_type(file_record: File) -> str:
        """Returns the preview type for a file."""
        if not file_record:
            return 'missing'

        if file_record.is_quarantined:
            return 'blocked'

        if getattr(file_record, 'is_encrypted', False):
            return 'encrypted'

        mime_type = file_record.mime_type or ''

        if mime_type.startswith('image/'):
            # Only support browser-native images
            if any(ext in mime_type for ext in ['png', 'jpeg', 'jpg', 'gif', 'webp']):
                return 'image'

        if mime_type == 'application/pdf':
            return 'pdf'

        if mime_type.startswith('video/'):
            # Browser native video formats
            if any(fmt in mime_type for fmt in ['mp4', 'webm', 'ogg']):
                return 'video'

        if mime_type.startswith('audio/'):
            # Browser native audio formats
            if any(fmt in mime_type for fmt in ['mpeg', 'wav', 'ogg', 'aac']):
                return 'audio'

        if mime_type == 'text/csv':
            return 'csv'

        if PreviewService.is_text_like(file_record):
            return 'text'

        # Office types
        office_mimes = [
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.oasis.opendocument.text',
            'application/vnd.oasis.opendocument.spreadsheet',
            'application/vnd.oasis.opendocument.presentation',
            'application/msword',
            'application/vnd.ms-excel',
            'application/vnd.ms-powerpoint'
        ]

        if any(m in mime_type for m in office_mimes) or \
           'officedocument.wordprocessingml' in mime_type or \
           'officedocument.spreadsheetml' in mime_type or \
           'officedocument.presentationml' in mime_type or \
           'oasis.opendocument' in mime_type:

            metadata = file_record.preview_metadata or {}
            status = metadata.get('office_preview_status', 'none')

            if status == 'ready':
                return 'office_pdf'
            elif status == 'pending':
                return 'office_pending'
            elif status == 'failed':
                return 'office_failed'
            else:
                return 'office_none'

        return 'unsupported'

    @staticmethod
    def is_previewable(file_record: File) -> bool:
        """Checks if a file is previewable in the browser.
        Note: For Office files, we only return True if the PDF is actually ready.
        Pending/Failed Office files are handled by the Web UI but not marked as 'previewable' for the API.
        """
        preview_type = PreviewService.get_preview_type(file_record)
        return preview_type in ['image', 'pdf', 'text', 'csv', 'video', 'audio', 'office_pdf']

    @staticmethod
    def get_safe_text_preview(file_record: File, max_chars: int = 100000) -> str:
        """Reads a safe, size-limited text preview from the file."""
        if PreviewService.get_preview_type(file_record) not in ['text', 'csv']:
            return ""

        full_path = storage_service.get_full_path(file_record.storage_path)
        if not os.path.exists(full_path):
            return "File not found in storage."

        try:
            # Read first max_chars characters
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read(max_chars)
        except Exception as e:
            current_app.logger.error(f"Error reading text preview: {e}")
            return "Error reading preview."

    @staticmethod
    def get_icon_type(file_record: File) -> str:
        """Returns the Bootstrap Icon name for the file type."""
        if not file_record:
            return "bi-file-earmark"

        mime_type = file_record.mime_type or ''

        if mime_type.startswith('image/'):
            return "bi-file-earmark-image"
        if mime_type == 'application/pdf':
            return "bi-file-earmark-pdf"
        if mime_type.startswith('video/'):
            return "bi-file-earmark-play"
        if mime_type.startswith('audio/'):
            return "bi-file-earmark-music"
        if mime_type in ['application/zip', 'application/x-zip-compressed']:
            return "bi-file-earmark-zip"
        if mime_type.startswith('text/'):
            return "bi-file-earmark-text"

        # Office types
        if 'word' in mime_type or 'officedocument.wordprocessingml' in mime_type or 'oasis.opendocument.text' in mime_type:
            return "bi-file-earmark-word"
        if 'excel' in mime_type or 'officedocument.spreadsheetml' in mime_type or 'oasis.opendocument.spreadsheet' in mime_type:
            return "bi-file-earmark-excel"
        if 'powerpoint' in mime_type or 'officedocument.presentationml' in mime_type or 'oasis.opendocument.presentation' in mime_type:
            return "bi-file-earmark-slides"

        return "bi-file-earmark"

preview_service = PreviewService()
