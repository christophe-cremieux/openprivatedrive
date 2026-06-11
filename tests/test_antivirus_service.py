"""
Description: Pytest module covering antivirus service.
Author: Your Christophe CREMIEUX <sammy.crem@gmail.com>
Copyright: (c) 2026 Christophe CREMIEUX

License: GNU Affero General Public License v3.0
         This program is free software: you can redistribute it and/or modify
         it under the terms of the GNU Affero General Public License as
         published by the Free Software Foundation.

         See the LICENSE file at the root of this project for details.
"""

import sys
import types

from app.models.system_stat import SystemStat
from app.services.antivirus_service import antivirus_service


def test_antivirus_service_detects_eicar_filename(app, tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"plain text")

    with app.app_context():
        monkeypatch.setitem(app.config, "ANTIVIRUS_ENABLED", False)
        result = antivirus_service.scan_file(sample, "eicar.txt")

    assert result.is_infected is True
    assert result.signature == "EICAR-Test-File"


def test_antivirus_service_uses_clamd_when_enabled(app, db, tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"plain text")

    class FakeClamdSocket:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def ping(self):
            return True

        def scan_file(self, path):
            assert path == str(sample)
            return {path: ("FOUND", "Test.Signature")}

    fake_pyclamd = types.SimpleNamespace(ClamdNetworkSocket=FakeClamdSocket)
    monkeypatch.setitem(sys.modules, "pyclamd", fake_pyclamd)
    monkeypatch.setattr("app.services.antivirus_service.os.path.exists", lambda path: False)

    with app.app_context():
        monkeypatch.setitem(app.config, "ANTIVIRUS_ENABLED", True)
        monkeypatch.setitem(app.config, "CLAMD_SOCKET", "")
        monkeypatch.setitem(app.config, "CLAMD_HOST", "clamav")
        monkeypatch.setitem(app.config, "CLAMD_PORT", 3310)
        result = antivirus_service.scan_file(sample, "sample.txt")

    assert result.is_infected is True
    assert result.signature == "Test.Signature"


def test_antivirus_service_uses_clamd_unix_socket_when_configured(app, db, tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"plain text")

    class FakeClamdUnixSocket:
        def __init__(self, socket_path):
            self.socket_path = socket_path

        def ping(self):
            return True

        def scan_file(self, path):
            assert self.socket_path == "/var/run/clamav/clamd.ctl"
            assert path == str(sample)
            return None

    def fail_network_socket(host, port):
        raise AssertionError("network socket should not be used when CLAMD_SOCKET is set")

    fake_pyclamd = types.SimpleNamespace(
        ClamdUnixSocket=FakeClamdUnixSocket,
        ClamdNetworkSocket=fail_network_socket,
    )
    monkeypatch.setitem(sys.modules, "pyclamd", fake_pyclamd)

    with app.app_context():
        monkeypatch.setitem(app.config, "ANTIVIRUS_ENABLED", True)
        monkeypatch.setitem(app.config, "CLAMD_SOCKET", "/var/run/clamav/clamd.ctl")
        result = antivirus_service.scan_file(sample, "sample.txt")

    assert result.is_infected is False


def test_antivirus_service_auto_detects_common_unix_socket(app, db, tmp_path, monkeypatch):
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"plain text")

    class FakeClamdUnixSocket:
        def __init__(self, socket_path):
            self.socket_path = socket_path

        def ping(self):
            return True

        def scan_file(self, path):
            assert self.socket_path == "/run/clamav/clamd.ctl"
            assert path == str(sample)
            return None

    def fake_exists(path):
        return path == "/run/clamav/clamd.ctl"

    fake_pyclamd = types.SimpleNamespace(
        ClamdUnixSocket=FakeClamdUnixSocket,
        ClamdNetworkSocket=lambda host, port: None,
    )
    monkeypatch.setitem(sys.modules, "pyclamd", fake_pyclamd)
    monkeypatch.setattr("app.services.antivirus_service.os.path.exists", fake_exists)

    with app.app_context():
        monkeypatch.setitem(app.config, "ANTIVIRUS_ENABLED", True)
        monkeypatch.setitem(app.config, "CLAMD_SOCKET", "")
        result = antivirus_service.scan_file(sample, "sample.txt")

    assert result.is_infected is False


def test_antivirus_service_uses_admin_global_setting(app, db, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "ANTIVIRUS_ENABLED", True)
        SystemStat.set_stat(antivirus_service.ENABLED_SETTING_KEY, False)

        assert antivirus_service.is_enabled() is False
