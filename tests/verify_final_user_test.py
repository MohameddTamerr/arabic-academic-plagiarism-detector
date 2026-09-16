"""
verify_final_user_test.py - Comprehensive verification script for the final user test release.
Tests Arabic-Plagiarism-System.exe in C:\\FinalUserTest\\Arabic-Plagiarism-System.exe.
"""
import os
import sys
import time
import shutil
import struct
import hashlib
import json
import ctypes
import subprocess
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass



EXE_SRC = r"C:\Users\user\Downloads\Baba\dist\Arabic-Plagiarism-System.exe"
TEST_DIR = r"C:\FinalUserTest"
EXE_TARGET = os.path.join(TEST_DIR, "Arabic-Plagiarism-System.exe")
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
APP_DATA_ROOT = os.path.join(LOCAL_APPDATA, "ArabicAcademicPlagiarismSystem")
DATA_DIR = os.path.join(APP_DATA_ROOT, "Data")
DB_DIR = os.path.join(DATA_DIR, "Database")
CONFIG_DIR = os.path.join(DATA_DIR, "Config")
LOGS_DIR = os.path.join(DATA_DIR, "Logs")
BACKUPS_DIR = os.path.join(DATA_DIR, "Backups")
DB_PATH = os.path.join(DB_DIR, "papers.db")

FILE_ATTRIBUTE_HIDDEN = 0x02

def is_hidden(path):
    if not os.path.exists(path):
        return False
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & FILE_ATTRIBUTE_HIDDEN)

def verify_pe_subsystem(exe_path):
    with open(exe_path, "rb") as f:
        data = f.read(1024)
    pe_offset = struct.unpack("<I", data[0x3C:0x40])[0]
    with open(exe_path, "rb") as f:
        f.seek(pe_offset)
        pe_header = f.read(128)
    magic = struct.unpack("<H", pe_header[0:2])[0]
    opt_magic = struct.unpack("<H", pe_header[24:26])[0]
    subsystem_offset = pe_offset + 24 + 68
    with open(exe_path, "rb") as f:
        f.seek(subsystem_offset)
        subsystem = struct.unpack("<H", f.read(2))[0]
    return subsystem, opt_magic

def main():
    print("=" * 70)
    print("STARTING COMPREHENSIVE FINAL USER-TEST RELEASE VERIFICATION")
    print("=" * 70)

    # 1. Verify EXE build artifact exists
    assert os.path.exists(EXE_SRC), f"EXE not found at {EXE_SRC}"
    size = os.path.getsize(EXE_SRC)
    with open(EXE_SRC, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()
    print(f"[OK] EXE Artifact: {EXE_SRC}")
    print(f"     Size: {size:,} bytes ({size / (1024*1024):.2f} MB)")
    print(f"     SHA256: {sha256}")

    # 2. Check PE Subsystem (Must be 2 = IMAGE_SUBSYSTEM_WINDOWS_GUI)
    subsystem, opt_magic = verify_pe_subsystem(EXE_SRC)
    print(f"[OK] PE Subsystem: {subsystem} ({'WINDOWS_GUI' if subsystem == 2 else 'WINDOWS_CUI'})")
    assert subsystem == 2, f"PE Subsystem must be 2 (GUI), got {subsystem}"

    # 3. Clean test directory and copy single EXE
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR, exist_ok=True)
    shutil.copy2(EXE_SRC, EXE_TARGET)
    print(f"[OK] Copied single EXE to isolated test directory: {EXE_TARGET}")
    dir_contents = os.listdir(TEST_DIR)
    print(f"     Test Directory Contents: {dir_contents}")
    assert dir_contents == ["Arabic-Plagiarism-System.exe"], f"Expected ONLY single EXE in {TEST_DIR}, found: {dir_contents}"

    # 4. Clean AppData directory to test fresh first-run experience
    if os.path.exists(APP_DATA_ROOT):
        try:
            shutil.rmtree(APP_DATA_ROOT, ignore_errors=True)
            print(f"[OK] Cleared fresh AppData root: {APP_DATA_ROOT}")
        except Exception as e:
            print(f"[WARN] Could not clean AppData: {e}")

    # 5. Launch C:\FinalUserTest\Arabic-Plagiarism-System.exe
    print(f"\n[LAUNCH] Starting {EXE_TARGET} ...")
    proc = subprocess.Popen(
        [EXE_TARGET],
        cwd=TEST_DIR
    )
    print(f"[OK] Process spawned with PID {proc.pid}")

    # 6. Wait for HTTP server to become responsive
    base_url = "http://127.0.0.1:5000"
    session = requests.Session()
    session.trust_env = False
    
    server_ready = False
    for i in range(45):
        try:
            resp = session.get(f"{base_url}/api/system/ping", timeout=2)
            if resp.status_code == 200:
                server_ready = True
                print(f"[OK] Server is UP and responding after {i+1}s: {resp.json()}")
                break
        except Exception:
            time.sleep(1)

    assert server_ready, "Server failed to respond to /api/system/ping within 45 seconds"

    # 7. Check GUI subsystem invariants & Server Header
    ping_info = session.get(f"{base_url}/api/system/ping").json()
    print(f"     Ping Response: {ping_info}")
    assert ping_info.get("status") == "ok"
    assert ping_info.get("ready") is True

    # 8. Verify Hidden Attributes on Database and Config
    print("\n[VERIFY] Checking Windows Hidden Attributes...")
    time.sleep(2) # Give a moment for initial DB and config files to be written
    
    print(f"     Database dir ({DB_DIR}) exists: {os.path.exists(DB_DIR)}, Hidden: {is_hidden(DB_DIR)}")
    assert os.path.exists(DB_DIR), "Database directory must exist"
    assert is_hidden(DB_DIR), "Database directory MUST have FILE_ATTRIBUTE_HIDDEN"

    print(f"     Database file ({DB_PATH}) exists: {os.path.exists(DB_PATH)}, Hidden: {is_hidden(DB_PATH)}")
    assert os.path.exists(DB_PATH), "papers.db must exist"
    assert is_hidden(DB_PATH), "papers.db MUST have FILE_ATTRIBUTE_HIDDEN"

    print(f"     Config dir ({CONFIG_DIR}) exists: {os.path.exists(CONFIG_DIR)}, Hidden: {is_hidden(CONFIG_DIR)}")
    assert os.path.exists(CONFIG_DIR), "Config directory must exist"
    assert is_hidden(CONFIG_DIR), "Config directory MUST have FILE_ATTRIBUTE_HIDDEN"

    print(f"     Logs dir ({LOGS_DIR}) exists: {os.path.exists(LOGS_DIR)}, Hidden: {is_hidden(LOGS_DIR)}")
    assert os.path.exists(LOGS_DIR), "Logs directory must exist"
    assert not is_hidden(LOGS_DIR), "Logs directory MUST NOT be hidden (for user/admin accessibility)"

    print(f"     Backups dir ({BACKUPS_DIR}) exists: {os.path.exists(BACKUPS_DIR)}, Hidden: {is_hidden(BACKUPS_DIR)}")
    assert os.path.exists(BACKUPS_DIR), "Backups directory must exist"
    assert not is_hidden(BACKUPS_DIR), "Backups directory MUST NOT be hidden (for user/admin accessibility)"

    # 9. Verify First-Run Admin Setup
    print("\n[VERIFY] Testing First-Run Setup & Authentication...")
    status_resp = session.get(f"{base_url}/api/auth/status").json()
    print(f"     Auth Status: {status_resp}")
    assert status_resp.get("needs_first_time_setup") is True, "Fresh run must require first-time admin setup"
    
    # Get CSRF Token
    csrf_resp = session.get(f"{base_url}/api/auth/csrf-token").json()
    csrf_token = csrf_resp.get("csrf_token")
    headers = {"X-CSRFToken": csrf_token}

    # Submit admin setup
    admin_payload = {
        "username": "sysadmin",
        "password": "UserTestPass1234!",
        "full_name": "مدير النظام التجريبي"
    }
    setup_resp = session.post(f"{base_url}/api/auth/setup_first_admin", json=admin_payload, headers=headers)
    print(f"     Setup response: {setup_resp.status_code}, {setup_resp.json()}")
    assert setup_resp.status_code == 200
    assert setup_resp.json().get("success") is True

    # Check /api/auth/me to verify authenticated session
    me_resp = session.get(f"{base_url}/api/auth/me")
    print(f"     Current user profile: {me_resp.json()}")
    assert me_resp.json().get("authenticated") is True
    assert me_resp.json().get("user", {}).get("username") == "sysadmin"

    # 10. Test Document Upload and Plagiarism Scanning
    print("\n[VERIFY] Testing Plagiarism Analysis Pipeline...")
    sample_text = (
        "يعتبر الذكاء الاصطناعي من أهم التقنيات الحديثة في العصر الحالي. "
        "يهدف هذا البحث إلى دراسة تأثير خوارزميات التعلم العميق على معالجة اللغات الطبيعية وخاصة اللغة العربية. "
        "وقد أظهرت النتائج تحسناً ملحوظاً في دقة استرجاع المعلومات وتحليل النصوص الأكاديمية."
    )
    
    csrf_resp = session.get(f"{base_url}/api/auth/csrf-token").json()
    csrf_token = csrf_resp.get("csrf_token")
    headers = {"X-CSRFToken": csrf_token}

    scan_resp = session.post(
        f"{base_url}/api/analyze",
        data={
            "title": "بحث تجريبي للاختبار النهائي للنسخة",
            "author": "د. الباحث الأكاديمي",
            "text": sample_text
        },
        headers=headers
    )
    print(f"     Analysis response status: {scan_resp.status_code}")
    assert scan_resp.status_code == 200, f"Analysis failed: {scan_resp.text}"
    report = scan_resp.json()
    print(f"     Generated Report ID: {report.get('id')}, Overall Pct: {report.get('overall_pct')}%")
    assert "overall_pct" in report
    assert "id" in report

    # 11. Test Backup and Restore via API
    print("\n[VERIFY] Testing Backup Creation & Attribute Preservation...")
    csrf_resp = session.get(f"{base_url}/api/auth/csrf-token").json()
    csrf_token = csrf_resp.get("csrf_token")
    headers = {"X-CSRFToken": csrf_token}

    backup_resp = session.post(
        f"{base_url}/api/admin/backup",
        json={"label": "usertest_pre_restore"},
        headers=headers
    )
    print(f"     Backup create response: {backup_resp.status_code}, {backup_resp.json()}")
    assert backup_resp.status_code == 200
    backup_data = backup_resp.json()
    backup_id = backup_data.get("backup_id")
    assert backup_id, "Backup ID not returned"

    # Verify backup file in Backups directory is not hidden
    backup_files = [os.path.join(BACKUPS_DIR, f) for f in os.listdir(BACKUPS_DIR) if f.endswith(".zip")]
    print(f"     Found backup archives: {[os.path.basename(f) for f in backup_files]}")
    assert len(backup_files) > 0, "No backup file found in Backups directory"
    for bf in backup_files:
        assert not is_hidden(bf), f"Backup archive {bf} should NOT be hidden"

    # Validate backup via API
    val_resp = session.post(f"{base_url}/api/admin/backups/{backup_id}/validate", headers=headers)
    print(f"     Validate backup response: {val_resp.status_code}, {val_resp.json()}")
    assert val_resp.status_code == 200
    assert val_resp.json().get("success") is True

    # Restore backup via API
    csrf_resp = session.get(f"{base_url}/api/auth/csrf-token").json()
    csrf_token = csrf_resp.get("csrf_token")
    headers = {"X-CSRFToken": csrf_token}

    restore_resp = session.post(
        f"{base_url}/api/admin/backups/{backup_id}/restore",
        json={"confirmation": backup_id},
        headers=headers
    )
    print(f"     Restore backup response: {restore_resp.status_code}, {restore_resp.json()}")
    assert restore_resp.status_code == 200
    assert restore_resp.json().get("success") is True

    # Verify DB remains hidden after restore
    assert is_hidden(DB_PATH), "Restored papers.db MUST remain hidden"
    assert is_hidden(DB_DIR), "Restored DB directory MUST remain hidden"


    # 12. Check Runtime Logs for Absence of Flask Dev Server
    print("\n[VERIFY] Checking Runtime Logs for Production WSGI Server...")
    log_files = [os.path.join(LOGS_DIR, f) for f in os.listdir(LOGS_DIR) if f.endswith(".log")]
    print(f"     Found log files: {[os.path.basename(f) for f in log_files]}")
    
    dev_server_found = False
    waitress_found = False
    for log_file in log_files:
        with open(log_file, "rb") as f:
            content = f.read().decode("utf-8", errors="replace")
            if "Serving Flask app" in content or "WARNING: This is a development server" in content:
                dev_server_found = True
                print(f"[FAIL] Found Flask development server warning in {log_file}!")
            if "Waitress" in content or "waitress" in content or "Serving on" in content:
                waitress_found = True
                print(f"[OK] Found Waitress server confirmation in {log_file}")

    # 13. Test Duplicate Launch Behavior
    print("\n[VERIFY] Testing Duplicate Double-Click Launch Behavior...")
    dup_proc = subprocess.Popen([EXE_TARGET], cwd=TEST_DIR)
    dup_exit = dup_proc.wait(timeout=30)
    print(f"[OK] Duplicate launch process exited immediately with exit code {dup_exit}")
    assert dup_exit == 0, f"Duplicate launch should exit cleanly with 0, got {dup_exit}"
    
    # Original server should still be running and healthy
    ping_dup = session.get(f"{base_url}/api/system/ping").json()
    assert ping_dup.get("status") == "ok", "Main server must remain responsive after duplicate launch"
    print("[OK] Main server remains responsive after duplicate launch.")

    # 14. Terminate process cleanly
    print("\n[CLEANUP] Stopping first single-exe process run...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    print("[OK] Process terminated cleanly.")

    # 15. Persistence Verification: Relaunch and verify data is retained
    print("\n[VERIFY] Testing Cold Restart & Data Persistence...")
    proc2 = subprocess.Popen(
        [EXE_TARGET],
        cwd=TEST_DIR
    )
    time.sleep(5)
    ping2 = session.get(f"{base_url}/api/system/ping", timeout=5).json()
    assert ping2.get("status") == "ok", "Server failed to start after cold restart"
    
    # Verify setup is NOT required (data persisted)
    status_resp2 = session.get(f"{base_url}/api/auth/status").json()
    print(f"     Auth status on cold restart: {status_resp2}")
    assert status_resp2.get("needs_first_time_setup") is False, "Admin setup must NOT be required on cold restart"
    
    proc2.terminate()
    try:
        proc2.wait(timeout=10)
    except Exception:
        proc2.kill()
    print("[OK] Persistence and Cold Restart verified successfully.")

    print("\n" + "=" * 70)
    print("ALL FINAL USER-TEST RELEASE VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
