"""
Description: Module for app/utils/validators.py.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import mimetypes
import zipfile
import io

# Magic numbers/Signatures
SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'\xff\xd8\xff': 'image/jpeg',
    b'%PDF-': 'application/pdf',
    b'PK\x03\x04': 'application/zip', # Also used for docx, xlsx, pptx, odt, ods, odp
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    # Audio/Video
    b'ID3': 'audio/mpeg',
    b'\xff\xfb': 'audio/mpeg', # MP3 frame sync
    b'RIFF': 'audio/wav', # Check for WAVE later
    b'OggS': 'application/ogg',
    b'fLaC': 'audio/flac',
    b'\x00\x00\x00\x18ftyp': 'video/mp4',
    b'\x00\x00\x00\x20ftyp': 'video/mp4',
    b'\x1a\x45\xdf\xa3': 'video/webm', # EBML header
}

def validate_file_signature(file_stream, filename, mime_type):
    """
    Validates file signature against extension and provided mime_type.
    file_stream must be seekable.
    """
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

    # Read first 8 bytes for signature
    file_stream.seek(0)
    header = file_stream.read(8)
    file_stream.seek(0)

    detected_mime = None
    for sig, mt in SIGNATURES.items():
        if header.startswith(sig):
            detected_mime = mt
            break

    if detected_mime:
        # Check if detected mime matches or is compatible
        if detected_mime == 'audio/wav':
             file_stream.seek(8)
             riff_type = file_stream.read(4)
             file_stream.seek(0)
             if riff_type == b'WAVE':
                 if mime_type != 'audio/wav' and mime_type != 'audio/x-wav':
                     raise ValueError(f"File signature indicates WAVE but MIME type is {mime_type}")
                 return True
             elif riff_type == b'WEBP':
                 if mime_type != 'image/webp':
                     raise ValueError(f"File signature indicates WebP but MIME type is {mime_type}")
                 return True
             else:
                 raise ValueError(f"File signature indicates RIFF ({riff_type.decode(errors='replace')}) but is not a supported type.")
        elif detected_mime == 'video/mp4':
             # mp4/m4a/mov all use ftyp, we just check if mime_type matches major categories
             if not (mime_type.startswith('video/') or mime_type.startswith('audio/')):
                  raise ValueError(f"File signature indicates MP4/FTYP but MIME type is {mime_type}")
             return True
        elif detected_mime == 'application/ogg':
             if not (mime_type.startswith('video/') or mime_type.startswith('audio/') or mime_type == 'application/ogg'):
                  raise ValueError(f"File signature indicates Ogg but MIME type is {mime_type}")
             return True

        if detected_mime == 'application/zip':
            # ZIP is compatible with office docs and opendocument
            allowed_office = {
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word/',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xl/',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'ppt/',
                'application/vnd.oasis.opendocument.text': 'mimetype',
                'application/vnd.oasis.opendocument.spreadsheet': 'mimetype',
                'application/vnd.oasis.opendocument.presentation': 'mimetype'
            }

            if mime_type in allowed_office:
                # Deep inspection of ZIP for Office structure
                try:
                    file_stream.seek(0)
                    with zipfile.ZipFile(io.BytesIO(file_stream.read())) as zf:
                        namelist = zf.namelist()
                        required_prefix = allowed_office[mime_type]
                        if mime_type.startswith('application/vnd.oasis.opendocument'):
                             # ODF must have 'mimetype' file and it should contain the mime type
                             if 'mimetype' not in namelist:
                                 raise ValueError(f"File claims to be ODF ({mime_type}) but 'mimetype' file is missing.")
                        else:
                             if not any(name.startswith(required_prefix) for name in namelist) or '[Content_Types].xml' not in namelist:
                                 raise ValueError(f"File claims to be Office document ({mime_type}) but internal structure is invalid.")
                    file_stream.seek(0)
                except zipfile.BadZipFile:
                    raise ValueError("File claims to be Office document but is not a valid ZIP.")
            elif mime_type != 'application/zip':
                raise ValueError(f"File signature indicates ZIP/Office but MIME type is {mime_type}")
        elif detected_mime != mime_type:
            # Allow some leeway if mimetypes guess was slightly different but same category?
            if not (detected_mime.startswith('image/') and mime_type.startswith('image/')):
                raise ValueError(f"File signature mismatch: detected {detected_mime}, but received {mime_type}")

    return True

def validate_resource_name(name, max_length=255):
    """
    Validates a file or folder name.
    Trims whitespace, rejects empty names, and rejects path separators.
    """
    if not name:
        raise ValueError("Name cannot be empty.")

    name = name.strip()

    if not name:
        raise ValueError("Name cannot consist only of whitespace.")

    if len(name) > max_length:
        raise ValueError(f"Name is too long (max {max_length} characters).")

    if '/' in name or '\\' in name:
        raise ValueError("Name cannot contain path separators (/ or \\).")

    return name
