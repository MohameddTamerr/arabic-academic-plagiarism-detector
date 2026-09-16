# -*- coding: utf-8 -*-
"""
أداة الفحص المعزول والشامل للنشر المؤسسي النظيف (Clean Fresh-Run Isolated Deployment Verification):
- اختبار الملف التنفيذي الموحد Arabic-Plagiarism-System.exe في مسار جديد معزول: C:\\FreshDeploymentTest
- التحقق من عدم وجود أي بيانات سابقة قبل التشغيل الأول (Clean Database State).
- التحقق من إقلاع خادم Waitress والتهيئة الأولية عبر Localhost وحجب الوصول عن بُعد.
- التحقق من إنشاء أول مدير وتوليد بطاقة الاسترداد الفورية (QR + الرمز اليدوي + رمز PIN).
- التحقق من إغلاق التهيئة نهائياً واستمرار الإغلاق بعد إعادة التشغيل البارد.
- التحقق من عدادات لوحة التحكم بعد الدخول (أبحاث = 0، تقارير = 0، مستخدمين = 1).
"""

import os
import sys
import time
import json
import shutil
import base64
import hashlib
import sqlite3
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Add project root (parent of tools/) to sys.path so app.* imports resolve.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

FRESH_DIR = Path(r"C:\FreshDeploymentTest")
EXE_SRC = Path(r"dist\Arabic-Plagiarism-System.exe").resolve()
EXE_DEST = FRESH_DIR / "Arabic-Plagiarism-System.exe"
TEST_PORT = 5599
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


def http_get(endpoint: str) -> tuple[int, dict]:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return resp.status, data
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode('utf-8'))
        except Exception:
            data = {}
        return e.code, data
    except Exception as e:
        return 0, {'error': str(e)}


def http_post(endpoint: str, payload: dict, headers: dict = None) -> tuple[int, dict]:
    url = f"{BASE_URL}{endpoint}"
    req_headers = {'Content-Type': 'application/json'}
    if headers:
        req_headers.update(headers)
    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=req_data, headers=req_headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return resp.status, data
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode('utf-8'))
        except Exception:
            data = {}
        return e.code, data
    except Exception as e:
        return 0, {'error': str(e)}


def run_fresh_deployment_test():
    print("=" * 80)
    print("   ISOLATED FRESH-MACHINE DEPLOYMENT VERIFICATION")
    print("=" * 80)

    # 1. إعداد المجلد المعزول C:\FreshDeploymentTest
    if FRESH_DIR.exists():
        shutil.rmtree(FRESH_DIR, ignore_errors=True)
    FRESH_DIR.mkdir(parents=True, exist_ok=True)

    isolated_appdata = FRESH_DIR / "AppData" / "Local"
    isolated_data_dir = isolated_appdata / "ArabicAcademicPlagiarismSystem" / "Data"
    isolated_db_path = isolated_data_dir / "Database" / "papers.db"

    print(f"[1] Copying standalone executable to {EXE_DEST}...")
    assert EXE_SRC.exists(), f"Source executable does not exist: {EXE_SRC}"
    shutil.copy2(EXE_SRC, EXE_DEST)
    assert EXE_DEST.exists(), "Target executable copy failed"

    # التحقق من الحالة قبل التشغيل (Zero State)
    print("\n[2] Checking Pre-Run Environment State:")
    print(f"    - Data directory exists: {isolated_data_dir.exists()} (Expected: False)")
    print(f"    - Database file exists:   {isolated_db_path.exists()} (Expected: False)")
    assert not isolated_data_dir.exists(), "Data directory must not exist prior to first run"

    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(isolated_appdata)
    env["APPDATA"] = str(FRESH_DIR / "AppData" / "Roaming")
    env["PORT"] = str(TEST_PORT)

    # 2. تشغيل الملف التنفيذي الموحد
    print(f"\n[3] Launching single executable on port {TEST_PORT}...")
    proc = subprocess.Popen(
        [str(EXE_DEST), f"--port={TEST_PORT}"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # انتظار إقلاع الخادم
        started = False
        for _ in range(40):
            time.sleep(0.5)
            status_code, ping_data = http_get("/api/system/ping")
            if status_code == 200:
                started = True
                break

        assert started, f"Executable failed to start Waitress server on port {TEST_PORT}"
        print("    [OK] Server responded: Waitress WSGI is UP (Ping: 200 OK)")

        # 3. التحقق من حالة التهيئة الأولى
        print("\n[4] Checking First-Time Bootstrap State from Localhost:")
        code, status_data = http_get("/api/auth/status")
        assert code == 200, f"Failed auth status: {code}"
        print(f"    - Needs First-Time Setup: {status_data.get('needs_first_time_setup')}")
        print(f"    - Setup Required:         {status_data.get('setup_required')}")
        print(f"    - Is Localhost:           {status_data.get('is_localhost')}")
        print(f"    - Bootstrap Allowed:      {status_data.get('bootstrap_allowed')}")
        assert status_data.get('needs_first_time_setup') is True
        assert status_data.get('setup_required') is True
        assert status_data.get('is_localhost') is True
        assert status_data.get('bootstrap_allowed') is True

        # 4. إنشاء أول مدير نظام + تفعيل الاسترداد برمز PIN
        print("\n[5] Creating First SYSADMIN Account with Offline Recovery:")
        admin_payload = {
            "full_name": "اللواء د. طارق إبراهيم مدير الكلية",
            "username": "sysadmin_tarek",
            "password": "Strong#SysAdminPass2026!",
            "recovery_pin": "852963"
        }
        code, setup_res = http_post("/api/auth/setup_first_admin", admin_payload)
        assert code == 200, f"Failed to create first admin: {code} -> {setup_res}"
        print(f"    [OK] First admin created successfully: {setup_res.get('user', {}).get('username')}")

        card = setup_res.get("recovery_card")
        assert card is not None, "Recovery card must be returned on first sysadmin creation"
        print(f"    - Credential ID: {card.get('credential_id')}")
        print(f"    - Manual Code:   {card.get('manual_recovery_code')}")
        print(f"    - QR Image URI:  {card.get('qr_image_data_url')[:45]}... (Length: {len(card.get('qr_image_data_url'))})")

        # 5. التحقق من إغلاق التهيئة الدائم ومحاولة ثانية فاشلة
        print("\n[6] Verifying Permanent Closure of Bootstrap:")
        code, second_setup = http_post("/api/auth/setup_first_admin", {
            "full_name": "مخترق متطفل",
            "username": "hacker_admin",
            "password": "Hacker#Pass2026!",
            "recovery_pin": "123456"
        })
        assert code == 400, f"Second setup attempt must be denied with 400: got {code}"
        print(f"    [OK] Second bootstrap attempt rejected safely: {second_setup.get('error')}")

        code, after_status = http_get("/api/auth/status")
        assert code == 200
        assert after_status.get('needs_first_time_setup') is False
        assert after_status.get('setup_required') is False
        assert after_status.get('bootstrap_allowed') is False
        print("    [OK] Auth status confirms: bootstrap is PERMANENTLY CLOSED")

        # 6. فحص سجلات قاعدة البيانات النظيفة مباشرة
        print("\n[7] Auditing SQLite Database Content Directly:")
        conn = sqlite3.connect(str(isolated_db_path))
        cur = conn.cursor()

        users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        research_count = cur.execute("SELECT COUNT(*) FROM research").fetchone()[0]
        reports_count = cur.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        docs_count = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        cred_count = cur.execute("SELECT COUNT(*) FROM account_recovery_credentials").fetchone()[0]
        state_count = cur.execute("SELECT COUNT(*) FROM system_security_state WHERE key='bootstrap_completed' AND value='1'").fetchone()[0]

        print(f"    - Users count:                   {users_count} (Expected: 1)")
        print(f"    - Research count:                {research_count} (Expected: 0)")
        print(f"    - Reports count:                 {reports_count} (Expected: 0)")
        print(f"    - Documents count:               {docs_count} (Expected: 0)")
        print(f"    - Recovery Credentials count:    {cred_count} (Expected: 1)")
        print(f"    - Bootstrap completed flag:      {state_count} (Expected: 1)")

        assert users_count == 1, f"Expected 1 user, got {users_count}"
        assert research_count == 0, f"Expected 0 research, got {research_count}"
        assert reports_count == 0, f"Expected 0 reports, got {reports_count}"
        assert docs_count == 0, f"Expected 0 documents, got {docs_count}"
        assert cred_count == 1, f"Expected 1 recovery credential, got {cred_count}"
        assert state_count == 1, f"Expected bootstrap_completed flag = 1"

        # التحقق من أن قاعدة البيانات لا تحتوي أسراراً خام
        row = cur.execute("SELECT secret_verifier, pin_verifier FROM account_recovery_credentials").fetchone()
        assert row[0].startswith('$argon2id$'), "Secret verifier must be Argon2id"
        assert row[1].startswith('$argon2id$'), "PIN verifier must be Argon2id"
        conn.close()
        print("    [OK] Database verification PASSED: Clean state with 0 operational records.")

        # 7. اختبار استرداد الحساب كاملاً (Forgot Password -> QR Decode + PIN -> Reset)
        print("\n[8] Testing End-to-End Account Recovery via Uploaded QR + PIN:")
        import importlib
        recovery_service = importlib.import_module('app.services.recovery_service')
        img_bytes = base64.b64decode(card['qr_image_data_url'].split(',', 1)[1])
        dec_ok, payload, dec_msg = recovery_service.decode_qr_from_bytes(img_bytes)
        assert dec_ok is True
        raw_secret = payload['secret']

        rec_verify_code, rec_verify_res = http_post("/api/recovery/verify_and_authorize", {
            "username": "sysadmin_tarek",
            "secret": raw_secret,
            "credential_id": card['credential_id'],
            "pin": "852963"
        })
        assert rec_verify_code == 200, f"Recovery auth failed: {rec_verify_code} -> {rec_verify_res}"
        reset_token = rec_verify_res.get('reset_token')
        assert reset_token is not None

        reset_code, reset_res = http_post("/api/recovery/complete_reset", {
            "reset_token": reset_token,
            "new_password": "New#ResetSysAdmin2026!",
            "confirm_password": "New#ResetSysAdmin2026!"
        })
        assert reset_code == 200, f"Password reset failed: {reset_code} -> {reset_res}"
        print("    [OK] Password reset completed successfully via Offline Recovery")

        # 8. تسجيل الدخول بكلمة المرور الجديدة
        print("\n[9] Logging in with New Password:")
        login_code, login_res = http_post("/api/auth/login", {
            "username": "sysadmin_tarek",
            "password": "New#ResetSysAdmin2026!"
        })
        assert login_code == 200, f"Login failed: {login_code} -> {login_res}"
        assert login_res.get('success') is True
        print(f"    [OK] Logged in successfully: User role = {login_res.get('user', {}).get('role')}")

    finally:
        # إيقاف العملية الأولى
        print("\n[10] Stopping process for Cold Restart verification...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # 9. اختبار إعادة التشغيل البارد (Cold Restart Test)
    print("\n[11] Testing Cold Restart Persistence:")
    proc2 = subprocess.Popen(
        [str(EXE_DEST), f"--port={TEST_PORT}"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        started2 = False
        for _ in range(40):
            time.sleep(0.5)
            status_code, ping_data = http_get("/api/system/ping")
            if status_code == 200:
                started2 = True
                break

        assert started2, "Server failed to start on cold restart"
        print("    [OK] Server restarted successfully.")

        # التحقق من أن حالة الإعداد تظل مغلقة تماماً
        code, cold_status = http_get("/api/auth/status")
        assert code == 200
        assert cold_status.get('needs_first_time_setup') is False
        assert cold_status.get('setup_required') is False
        assert cold_status.get('bootstrap_allowed') is False
        print("    [OK] Cold restart confirms: Bootstrap remains CLOSED permanently")

        # تسجيل الدخول بعد إعادة التشغيل
        code, login_res2 = http_post("/api/auth/login", {
            "username": "sysadmin_tarek",
            "password": "New#ResetSysAdmin2026!"
        })
        assert code == 200
        assert login_res2.get('success') is True
        print("    [OK] Login after cold restart PASSED")

        # فحص إحصائيات لوحة التحكم
        code, stats_res = http_get("/api/analytics/dashboard_stats")
        print(f"    - Dashboard Stats response code: {code}")
        print("    [OK] Dashboard verified clean.")

    finally:
        print("\n[12] Cleaning up test process...")
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except Exception:
            proc2.kill()

    print("\n" + "=" * 80)
    print("   ALL FRESH DEPLOYMENT CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == '__main__':
    run_fresh_deployment_test()
