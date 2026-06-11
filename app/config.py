"""
Description: Defines application configuration values and environment-aware Flask and SQLAlchemy settings.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / ".env")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-will-never-guess"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "sqlite:///" + str(basedir / "instance" / "app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    STORAGE_PATH = os.environ.get("STORAGE_PATH") or str(basedir / "storage")
    LOG_FILE_PATH = os.environ.get("LOG_FILE_PATH")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 500)) * 1024 * 1024

    # Security headers and cookie settings
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    # Rate limiting configuration
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "5 per minute")
    PUBLIC_LINK_RATE_LIMIT = os.environ.get("PUBLIC_LINK_RATE_LIMIT", "10 per minute")
    API_RATE_LIMIT = os.environ.get("API_RATE_LIMIT", "100 per minute")

    ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", 15))
    REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", 30))

    # Password Policy
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", 12))
    PASSWORD_RESET_TOKEN_MINUTES = int(os.environ.get("PASSWORD_RESET_TOKEN_MINUTES", 60))

    # Public Upload Config
    PUBLIC_UPLOAD_MAX_FILES = int(os.environ.get("PUBLIC_UPLOAD_MAX_FILES", 25))
    PUBLIC_UPLOAD_MAX_MB = int(os.environ.get("PUBLIC_UPLOAD_MAX_MB", 100))
    ZIP_EXPORT_MAX_MB = int(os.environ.get("ZIP_EXPORT_MAX_MB", 250))
    ZIP_EXTRACT_MAX_FILES = int(os.environ.get("ZIP_EXTRACT_MAX_FILES", 1500))
    ZIP_EXTRACT_MAX_TOTAL_MB = int(os.environ.get("ZIP_EXTRACT_MAX_TOTAL_MB", 1024))
    ZIP_EXTRACT_MAX_SINGLE_FILE_MB = int(os.environ.get("ZIP_EXTRACT_MAX_SINGLE_FILE_MB", 1500))
    ZIP_EXTRACT_MAX_DEPTH = int(os.environ.get("ZIP_EXTRACT_MAX_DEPTH", 20))
    ZIP_EXTRACT_MAX_RATIO = int(os.environ.get("ZIP_EXTRACT_MAX_RATIO", 100))
    SEARCH_MAX_PER_PAGE = int(os.environ.get("SEARCH_MAX_PER_PAGE", 100))
    DRIVE_PAGE_SIZE = int(os.environ.get("DRIVE_PAGE_SIZE", 50))

    ALLOWED_EXTENSIONS = {
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'txt', 'csv', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'zip',
        'odt', 'ods', 'odp',
        # Audio
        'mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac',
        # Video
        'mp4', 'webm', 'ogv', 'mov'
    }

    BLOCKED_EXTENSIONS = {
        'php', 'py', 'sh', 'exe', 'bat', 'cmd', 'js', 'html', 'svg',
        'dll', 'com', 'jar', 'ps1', 'vbs', 'wsf', 'csh', 'pl', 'rb', 'cgi', 'msi', 'scr', 'lnk'
    }

    # Admin credentials
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Office Preview Config
    OFFICE_PREVIEW_ENABLED = os.environ.get("OFFICE_PREVIEW_ENABLED", "True").lower() == "true"
    LIBREOFFICE_BIN = os.environ.get("LIBREOFFICE_BIN", "/usr/bin/libreoffice")
    OFFICE_PREVIEW_MAX_MB = int(os.environ.get("OFFICE_PREVIEW_MAX_MB", 50))
    OFFICE_PREVIEW_TIMEOUT_SECONDS = int(os.environ.get("OFFICE_PREVIEW_TIMEOUT_SECONDS", 30))

    # Encryption Config
    ENCRYPTED_FILES_ENABLED = os.environ.get("ENCRYPTED_FILES_ENABLED", "True").lower() == "true"
    ENCRYPTION_KDF_N = int(os.environ.get("ENCRYPTION_KDF_N", 32768))
    ENCRYPTION_KDF_R = int(os.environ.get("ENCRYPTION_KDF_R", 8))
    ENCRYPTION_KDF_P = int(os.environ.get("ENCRYPTION_KDF_P", 1))
    ENCRYPTION_MIN_PASSWORD_LENGTH = int(os.environ.get("ENCRYPTION_MIN_PASSWORD_LENGTH", 12))
    DECRYPT_RATE_LIMIT = os.environ.get("DECRYPT_RATE_LIMIT", "5 per minute")

    # DB Pool Config
    SQLALCHEMY_POOL_SIZE = int(os.environ.get("SQLALCHEMY_POOL_SIZE", 20))
    SQLALCHEMY_MAX_OVERFLOW = int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", 40))
    SQLALCHEMY_POOL_TIMEOUT = int(os.environ.get("SQLALCHEMY_POOL_TIMEOUT", 60))

    # Background Executor Config
    EXECUTOR_MAX_WORKERS = int(os.environ.get("EXECUTOR_MAX_WORKERS", 10))

    # Antivirus Config
    ANTIVIRUS_ENABLED = os.environ.get("ANTIVIRUS_ENABLED", "False").lower() == "true"
    CLAMD_SOCKET = os.environ.get("CLAMD_SOCKET", "")
    CLAMD_HOST = os.environ.get("CLAMD_HOST", "localhost")
    CLAMD_PORT = int(os.environ.get("CLAMD_PORT", 3310))

    # Video Thumbnails
    FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

    @classmethod
    def get_ffmpeg_bin(cls):
        """Best effort to find ffmpeg, supporting static-ffmpeg if installed."""
        if os.path.exists(cls.FFMPEG_BIN):
            return cls.FFMPEG_BIN
        try:
            from static_ffmpeg import run
            ffmpeg, _ = run.get_or_fetch_platform_executables_else_raise()
            return ffmpeg
        except (ImportError, Exception):
            return cls.FFMPEG_BIN
