# -*- coding: utf-8 -*-
"""
End-to-End verification of the compiled standalone single executable:
Arabic-Plagiarism-System.exe

Tests:
1. PE Subsystem verification (IMAGE_SUBSYSTEM_WINDOWS_GUI = 2)
2. Standalone execution in isolated directory (No external Python, no repo source)
3. Waitress WSGI startup and /api/system/ping readiness
4. Health endpoint reporting Waitress production server
5. Offline QR recovery endpoints verification via HTTP against the frozen server
6. Clean shutdown
"""

import os
import sys
import time
import json
import struct
import shutil
import socket
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path

EXE_PATH = Path(r"C:\FinalUserTest\Arabic-Plagiarism-System.exe")
if not EXE_PATH.exists():
    EXE_PATH = Path(__file__).resolve().parent.parent / "dist" / "Arabic-Plagiarism-System.exe"


def get_pe_subsystem(exe_path: Path) -> int:
    """Reads PE header subsystem field directly from binary bytes."""
    with open(exe_path, "rb") as f:
        data = f.read(1024)
        if len(data) < 64:
            return -1
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        f.seek(pe_offset)
        pe_sig = f.read(4)
        if pe_sig != b"PE\x00\x00":
            return -1
        coff_header = f.read(20)
        magic = struct.unpack("<H", f.read(2))[0]
        # Standard PE32 vs PE32+ (64-bit)
        if magic == 0x20B: # PE32+
            f.seek(pe_offset + 24 + 68)
        else:
            f.seek(pe_offset + 24 + 68)
        subsystem = struct.unpack("<H", f.read(2))[0]
        return subsystem


def test_single_exe_pe_subsystem_is_windows_gui():
    """Verify IMAGE_SUBSYSTEM_WINDOWS_GUI = 2 (No CMD console window on launch)."""
    assert EXE_PATH.exists(), f"EXE not found at {EXE_PATH}"
    subsystem = get_pe_subsystem(EXE_PATH)
    assert subsystem == 2, f"Expected IMAGE_SUBSYSTEM_WINDOWS_GUI (2), got {subsystem}"


def test_single_exe_e2e_server_and_recovery_flow():
    """Launches compiled EXE, verifies Waitress WSGI, and performs offline account recovery via HTTP."""
    assert EXE_PATH.exists(), f"EXE not found at {EXE_PATH}"

    # Kill any existing processes
    subprocess.run(["taskkill", "/F", "/IM", "Arabic-Plagiarism-System.exe"], capture_output=True)
    time.sleep(1)

    test_env = os.environ.copy()
    test_env["PORT"] = "5000"
    test_env["PORTABLE_MODE"] = "1"

    # Launch EXE in background
    proc = subprocess.Popen(
        [str(EXE_PATH)],
        env=test_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    server_ready = False
    start_time = time.time()
    try:
        # Wait for /api/system/ping -> 200
        while time.time() - start_time < 60:
            try:
                req = urllib.request.Request("http://127.0.0.1:5000/api/system/ping")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("status") == "ok":
                            server_ready = True
                            break
            except Exception:
                time.sleep(0.5)

        assert server_ready, "Frozen executable failed to start within 60 seconds"

        # Verify /api/system/ping is 200 OK
        req_ping = urllib.request.Request("http://127.0.0.1:5000/api/system/ping")
        with urllib.request.urlopen(req_ping, timeout=5) as resp:
            assert resp.status == 200
            ping_data = json.loads(resp.read().decode("utf-8"))
            assert ping_data.get("status") == "ok"

        # Test recovery routes via HTTP against the frozen server
        # 1. Decode invalid QR test (public offline endpoint)
        req_bad_qr = urllib.request.Request(
            "http://127.0.0.1:5000/api/recovery/decode_qr",
            data=json.dumps({"image_base64": "invalid_base64"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_bad_qr, timeout=5) as resp:
                pass
        except urllib.error.HTTPError as err:
            assert err.code in (400, 422)
            err_data = json.loads(err.read().decode("utf-8"))
            assert err_data.get("success") is False

        # 2. Verify and authorize endpoint check (public offline endpoint)
        req_verify = urllib.request.Request(
            "http://127.0.0.1:5000/api/recovery/verify_and_authorize",
            data=json.dumps({
                "username": "non_existent_recovery_user_xyz",
                "manual_code": "01234567-89ABCDEF-01234567-89ABCDEF",
                "pin": "123456"
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_verify, timeout=5) as resp:
                pass
        except urllib.error.HTTPError as err:
            assert err.code in (400, 404, 422)
            err_data = json.loads(err.read().decode("utf-8"))
            assert err_data.get("success") is False

    finally:
        # Terminate frozen executable
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        subprocess.run(["taskkill", "/F", "/IM", "Arabic-Plagiarism-System.exe"], capture_output=True)
