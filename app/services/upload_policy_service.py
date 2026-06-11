"""
Description: Service layer implementation for UploadPolicyService.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import re

from flask import current_app

from app.models.system_stat import SystemStat


class UploadPolicyService:
    ENABLED_KEY = "upload_policy_enabled"
    CUSTOM_ALLOWED_KEY = "custom_allowed_extensions"
    CUSTOM_BLOCKED_KEY = "custom_blocked_extensions"
    EXTENSION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,19}$")

    @classmethod
    def normalize_extensions(cls, raw_value):
        if not raw_value:
            return []

        if isinstance(raw_value, str):
            candidates = raw_value.replace("\n", ",").replace(" ", ",").split(",")
        else:
            candidates = raw_value

        extensions = []
        for candidate in candidates:
            ext = str(candidate).strip().lower().lstrip(".")
            if not ext:
                continue
            if not cls.EXTENSION_RE.match(ext):
                raise ValueError(f"Invalid extension: .{ext}")
            if ext not in extensions:
                extensions.append(ext)
        return extensions

    @classmethod
    def get_base_allowed_extensions(cls):
        return set(current_app.config.get("ALLOWED_EXTENSIONS", []))

    @classmethod
    def get_base_blocked_extensions(cls):
        return set(current_app.config.get("BLOCKED_EXTENSIONS", []))

    @classmethod
    def is_enabled(cls):
        return bool(SystemStat.get_stat(cls.ENABLED_KEY, True))

    @classmethod
    def get_custom_allowed_extensions(cls):
        return set(SystemStat.get_stat(cls.CUSTOM_ALLOWED_KEY, []))

    @classmethod
    def get_custom_blocked_extensions(cls):
        return set(SystemStat.get_stat(cls.CUSTOM_BLOCKED_KEY, []))

    @classmethod
    def get_allowed_extensions(cls):
        blocked = cls.get_blocked_extensions()
        allowed = cls.get_base_allowed_extensions() | cls.get_custom_allowed_extensions()
        return allowed - blocked

    @classmethod
    def get_blocked_extensions(cls):
        return cls.get_base_blocked_extensions() | cls.get_custom_blocked_extensions()

    @classmethod
    def get_policy(cls):
        blocked = cls.get_blocked_extensions()
        base_allowed = cls.get_base_allowed_extensions()
        custom_allowed = cls.get_custom_allowed_extensions()
        return {
            "enabled": cls.is_enabled(),
            "base_allowed": sorted(base_allowed),
            "custom_allowed": sorted(custom_allowed),
            "allowed": sorted((base_allowed | custom_allowed) - blocked),
            "base_blocked": sorted(cls.get_base_blocked_extensions()),
            "custom_blocked": sorted(cls.get_custom_blocked_extensions()),
            "blocked": sorted(blocked),
        }

    @classmethod
    def validate_extension(cls, extension):
        ext = str(extension or "").strip().lower().lstrip(".")
        blocked = cls.get_blocked_extensions()

        if ext in blocked:
            raise ValueError(f"Extension .{ext} is blocked for security reasons.")
        if not cls.is_enabled():
            return ext

        allowed = cls.get_allowed_extensions()
        if ext not in allowed:
            raise ValueError(f"Extension .{ext} is not allowed.")
        return ext

    @classmethod
    def set_enabled(cls, enabled):
        SystemStat.set_stat(cls.ENABLED_KEY, bool(enabled))

    @classmethod
    def save_custom_allowed_extensions(cls, raw_value):
        extensions = cls.normalize_extensions(raw_value)
        blocked = cls.get_blocked_extensions()
        conflicts = sorted(set(extensions) & blocked)
        if conflicts:
            raise ValueError(
                "Blocked extensions cannot be allowed: "
                + ", ".join(f".{ext}" for ext in conflicts)
            )
        SystemStat.set_stat(cls.CUSTOM_ALLOWED_KEY, extensions)
        return extensions

    @classmethod
    def save_custom_blocked_extensions(cls, raw_value):
        extensions = cls.normalize_extensions(raw_value)
        SystemStat.set_stat(cls.CUSTOM_BLOCKED_KEY, extensions)
        return extensions

    @classmethod
    def save_policy(cls, custom_allowed_value, custom_blocked_value):
        custom_allowed = cls.normalize_extensions(custom_allowed_value)
        custom_blocked = cls.normalize_extensions(custom_blocked_value)

        blocked = cls.get_base_blocked_extensions() | set(custom_blocked)
        conflicts = sorted(set(custom_allowed) & blocked)
        if conflicts:
            raise ValueError(
                "Blocked extensions cannot be allowed: "
                + ", ".join(f".{ext}" for ext in conflicts)
            )

        SystemStat.set_stat(cls.CUSTOM_BLOCKED_KEY, custom_blocked)
        SystemStat.set_stat(cls.CUSTOM_ALLOWED_KEY, custom_allowed)
        return cls.get_policy()


upload_policy_service = UploadPolicyService()
