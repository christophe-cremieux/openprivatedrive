"""
Description: Service layer implementation for AntivirusScanResult.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from flask import current_app


@dataclass(frozen=True)
class AntivirusScanResult:
    is_infected: bool
    signature: str | None = None
    error: str | None = None


class AntivirusService:
    ENABLED_SETTING_KEY = "antivirus_enabled"
    STRICT_MODE_SETTING_KEY = "antivirus_strict_mode" # Block pending scans
    COMMON_SOCKET_PATHS = (
        "/var/run/clamav/clamd.ctl",
        "/run/clamav/clamd.ctl",
        "/var/run/clamd.scan/clamd.sock",
        "/run/clamd.scan/clamd.sock",
        "/var/run/clamd.sock",
        "/run/clamd.sock",
    )

    def is_enabled(self) -> bool:
        """Return the admin-managed antivirus state, falling back to env config."""
        from app.models.system_stat import SystemStat

        default_enabled = bool(current_app.config.get("ANTIVIRUS_ENABLED"))
        return bool(SystemStat.get_stat(self.ENABLED_SETTING_KEY, default_enabled))

    def is_strict_mode(self) -> bool:
        """Return True if downloads should be blocked for files with pending scans."""
        from app.models.system_stat import SystemStat
        return bool(SystemStat.get_stat(self.STRICT_MODE_SETTING_KEY, False))

    def get_connection_label(self) -> str:
        socket_path = self.get_socket_path()
        if socket_path:
            return f"unix socket {socket_path}"

        host = current_app.config.get("CLAMD_HOST", "localhost")
        port = current_app.config.get("CLAMD_PORT", 3310)
        return f"network {host}:{port}"

    def get_socket_path(self) -> str | None:
        configured_socket = current_app.config.get("CLAMD_SOCKET")
        if configured_socket:
            return configured_socket

        for socket_path in self.COMMON_SOCKET_PATHS:
            if os.path.exists(socket_path):
                return socket_path

        return None

    def scan_file(self, path: str | Path, original_filename: str = "") -> AntivirusScanResult:
        """Scan a stored file with local checks and optional ClamAV daemon."""
        file_path = Path(path)

        local_result = self._scan_eicar(file_path, original_filename)
        if local_result.is_infected:
            return local_result

        if not self.is_enabled():
            return AntivirusScanResult(is_infected=False)

        return self._scan_with_clamav(file_path)

    def _scan_eicar(self, path: Path, original_filename: str) -> AntivirusScanResult:
        if "eicar" in original_filename.lower():
            return AntivirusScanResult(is_infected=True, signature="EICAR-Test-File")

        if not path.exists():
            return AntivirusScanResult(is_infected=False)

        try:
            with path.open("rb") as file_obj:
                content = file_obj.read(1024)
        except OSError:
            return AntivirusScanResult(is_infected=False)

        if b"EICAR" in content.upper():
            return AntivirusScanResult(is_infected=True, signature="EICAR-Test-File")

        return AntivirusScanResult(is_infected=False)

    def _scan_with_clamav(self, path: Path) -> AntivirusScanResult:
        try:
            import pyclamd
        except ImportError as exc:
            raise RuntimeError("ANTIVIRUS_ENABLED but 'pyclamd' is not installed.") from exc

        socket_path = self.get_socket_path()
        if socket_path:
            scanner = pyclamd.ClamdUnixSocket(socket_path)
        else:
            scanner = pyclamd.ClamdNetworkSocket(
                current_app.config.get("CLAMD_HOST", "localhost"),
                current_app.config.get("CLAMD_PORT", 3310),
            )
        if not scanner.ping():
            raise RuntimeError(f"ClamAV daemon did not respond using {self.get_connection_label()}.")

        scan_result = scanner.scan_file(os.fspath(path))
        if not scan_result:
            return AntivirusScanResult(is_infected=False)

        first_result = next(iter(scan_result.values()))
        status = first_result[0] if len(first_result) > 0 else None
        signature = first_result[1] if len(first_result) > 1 else None

        return AntivirusScanResult(is_infected=status == "FOUND", signature=signature)


antivirus_service = AntivirusService()
