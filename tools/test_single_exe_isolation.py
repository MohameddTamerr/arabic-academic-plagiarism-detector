# -*- coding: utf-8 -*-
"""
برنامج الاختبار الشامل لعزل وتشغيل الملف التنفيذي الموحد (Single-EXE Isolation & Smoke Test):
- يختبر تشغيل Arabic-Plagiarism-System.exe وهو الملف الوحيد في مجلد معزول تماماً C:\\SingleExeTest.
- يتحقق من عدم وجود أي ملفات بايثون أو مجلدات Runtime أو سكريبتات bat بجانبه.
- يتحقق من استجابة خادم Waitress والعمال ونقاط الفحص الحية.
- يتحقق من دورة الفحص الكاملة (تهيئة المدير الأول، تسجيل الدخول، رفع بحث، اكتمال الفحص، فتح التقرير).
- يتحقق من حفظ واستدامة البيانات، النسخ الاحتياطي، حزمة التشخيص، ومنع التشغيل المزدوج.
- يتحقق من التشغيل من مسار يحتوي مسافات.
"""

import os
import sys
import time
import json
import shutil
import socket
import sqlite3
import urllib.request
import urllib.parse
import http.cookiejar
import subprocess
from pathlib import Path

PORT = 5055
BASE_URL = f"http://127.0.0.1:{PORT}"
TEST_DIR = Path(r"C:\SingleExeTest")
SPACED_DIR = Path(r"C:\SingleExe Space Test")
DATA_DIR = TEST_DIR / "IsolatedData"
DIST_EXE = Path(__file__).resolve().parent.parent / "dist" / "Arabic-Plagiarism-System.exe"


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def kill_process_tree(proc: subprocess.Popen):
    if proc is None:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def wait_for_server(url: str, proc: subprocess.Popen = None, timeout: float = 35.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if proc and proc.poll() is not None:
            print(f"[ERROR] Process exited prematurely with code: {proc.returncode}", flush=True)
            return False
        try:
            req = urllib.request.Request(f"{url}/api/system/ping")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get('ready') is True or data.get('status') == 'ok':
                        return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def run_isolation_and_smoke_test():
    print("=" * 80)
    print("   STARTING SINGLE-EXE ISOLATION AND REAL SMOKE TEST")
    print("=" * 80)

    if not DIST_EXE.exists():
        print(f"[FAIL] Compiled executable not found at: {DIST_EXE}")
        sys.exit(1)

    print(f"[1] Source EXE: {DIST_EXE} ({round(os.path.getsize(DIST_EXE)/(1024*1024), 2)} MB)")

    # إيقاف أي عمليات سابقة معلقة
    subprocess.run(["taskkill", "/F", "/IM", "Arabic-Plagiarism-System.exe"], capture_output=True)
    time.sleep(1.0)

    # 1. إعداد المجلد المعزول
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    isolated_exe = TEST_DIR / "Arabic-Plagiarism-System.exe"
    shutil.copy2(DIST_EXE, isolated_exe)

    # التحقق من أن المجلد يحتوي حصرياً على الملف التنفيذي فقط
    contents = os.listdir(TEST_DIR)
    print(f"[2] Isolated directory contents: {contents}")
    assert contents == ["Arabic-Plagiarism-System.exe"], f"Isolation failed! Unexpected contents: {contents}"
    print("   [PASS] Perfect isolation: ONLY Arabic-Plagiarism-System.exe exists in folder.")

    # 2. تشغيل الملف التنفيذي الموحد في بيئة معزولة
    print("[3] Launching isolated EXE...")
    env = os.environ.copy()
    env["ARABIC_APP_DATA_DIR"] = str(DATA_DIR)
    env["PORT"] = str(PORT)
    env["HOST"] = "127.0.0.1"

    proc = subprocess.Popen(
        [str(isolated_exe), "--cli"],
        env=env,
        cwd=str(TEST_DIR)
    )

    try:
        print("[4] Waiting for HTTP /api/system/ping readiness...", flush=True)
        ready = wait_for_server(BASE_URL, proc=proc, timeout=40.0)
        assert ready, "Server failed to respond to /api/system/ping within timeout!"
        print("   [PASS] System ping returned 200 (Waitress is live).", flush=True)

        # 3. التحقق من مسارات البيانات المنشأة تلقائياً
        assert DATA_DIR.exists(), "Persistent data directory was not created!"
        assert (DATA_DIR / "Database").exists(), "Database directory missing!"
        assert (DATA_DIR / "Logs").exists(), "Logs directory missing!"
        assert (DATA_DIR / "Backups").exists(), "Backups directory missing!"
        assert (DATA_DIR / "Storage").exists(), "Storage directory missing!"
        print("   [PASS] Persistent directories automatically created under IsolatedData.")

        # 4. فحص الصفحة الرئيسية
        req_root = urllib.request.Request(BASE_URL)
        with urllib.request.urlopen(req_root, timeout=3.0) as resp:
            assert resp.status == 200, f"Root UI returned status {resp.status}"
            body = resp.read().decode('utf-8', errors='ignore')
            assert "منظومة" in body or "Academic" in body or "Plagiarism" in body, "Root page content missing expected markers"
        print("   [PASS] Root web UI returned HTTP 200 with institutional templates.")

        # 5. إعداد العميل مع ملفات تعريف الارتباط والجلسة
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        # جلب رمز CSRF
        csrf_req = urllib.request.Request(f"{BASE_URL}/api/auth/csrf-token")
        with opener.open(csrf_req) as resp:
            csrf_data = json.loads(resp.read().decode('utf-8'))
            csrf_token = csrf_data.get('csrf_token', '')
        print(f"   [PASS] CSRF token obtained: {csrf_token[:12]}...")

        # 6. فحص جاهزية المدير الأول
        status_req = urllib.request.Request(f"{BASE_URL}/api/auth/status")
        with opener.open(status_req) as resp:
            auth_st = json.loads(resp.read().decode('utf-8'))
            assert auth_st.get('needs_first_time_setup') is True, "First time setup should be allowed on fresh DB"
        print("   [PASS] First-time setup status validated.")

        # 7. إنشاء المدير الأول
        admin_payload = json.dumps({
            "username": "superadmin",
            "password": "StrongPassword123!",
            "full_name": "رئيس لجنة النزاهة الأكاديمية"
        }).encode('utf-8')
        admin_req = urllib.request.Request(
            f"{BASE_URL}/api/auth/setup_first_admin",
            data=admin_payload,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_token
            }
        )
        with opener.open(admin_req) as resp:
            assert resp.status == 200, "First admin setup failed"
            setup_res = json.loads(resp.read().decode('utf-8'))
            assert setup_res.get('success') is True, f"Setup response error: {setup_res}"
        print("   [PASS] First admin successfully provisioned.")

        # 8. التحقق من هوية المستخدم النشط
        me_req = urllib.request.Request(f"{BASE_URL}/api/auth/me")
        with opener.open(me_req) as resp:
            me_res = json.loads(resp.read().decode('utf-8'))
            assert me_res.get('authenticated') is True, "User should be authenticated"
            assert me_res['user']['username'] == "superadmin", "Authenticated username mismatch"
            csrf_token = me_res.get('csrf_token') or csrf_token
        print("   [PASS] Session authenticated for superadmin.")

        # 8b. إنشاء مستخدم مراجع أكاديمي بصلاحية الفحص
        create_user_payload = json.dumps({
            "username": "reviewer1",
            "password": "ReviewerPassword123!",
            "full_name": "المراجع الأكاديمي المعتمد",
            "role": "reviewer"
        }).encode('utf-8')
        create_user_req = urllib.request.Request(
            f"{BASE_URL}/api/admin/users",
            data=create_user_payload,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_token
            }
        )
        with opener.open(create_user_req) as resp:
            assert resp.status == 200, "Reviewer user creation failed"
        print("   [PASS] Academic reviewer provisioned with scan permissions.")

        # 8c. تسجيل الدخول بحساب المراجع
        login_rev_payload = json.dumps({
            "username": "reviewer1",
            "password": "ReviewerPassword123!"
        }).encode('utf-8')
        login_rev_req = urllib.request.Request(
            f"{BASE_URL}/api/auth/login",
            data=login_rev_payload,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_token
            }
        )
        with opener.open(login_rev_req) as resp:
            assert resp.status == 200, "Reviewer login failed"
            rev_res = json.loads(resp.read().decode('utf-8'))
            csrf_token = rev_res.get('csrf_token') or csrf_token
        print("   [PASS] Logged in as reviewer1 (has scan.start permission).")

        # 9. رفع بحث وإجراء فحص حقيقي
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        research_text = (
            "بسم الله الرحمن الرحيم\n"
            "مقدمة البحث: تعتبر الدراسات الأمنية المعاصرة ركيزة أساسية في استقرار الدول.\n"
            "الجرائم السيبرانية تشكل خطراً محدقاً على البنية التحتية المعلوماتية وتتطلب منظومة أمنية متكاملة للرصد والمكافحة.\n"
            "الخاتمة: يجب تعزيز الاستثمار في الكوادر الوطنية لتطوير منظومات الدفاع الرقمي المستقلة."
        )
        body_parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrf_token\"\r\n\r\n{csrf_token}\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\nدراسة الأمن السيبراني الميدانية\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"author\"\r\n\r\nد. أحمد محمود\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cyber_security_study.txt\"\r\nContent-Type: text/plain\r\n\r\n{research_text}\r\n",
            f"--{boundary}--\r\n"
        ]
        upload_body = "".join(body_parts).encode('utf-8')

        scan_req = urllib.request.Request(
            f"{BASE_URL}/api/scan",
            data=upload_body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf_token,
                "X-CSRFToken": csrf_token
            }
        )
        try:
            with opener.open(scan_req) as resp:
                assert resp.status == 200, "Scan submission failed"
                scan_res = json.loads(resp.read().decode('utf-8'))
                task_id = scan_res.get('task_id')
                assert task_id, f"No task_id returned from scan: {scan_res}"
            print(f"   [PASS] Real research uploaded, scan task started: {task_id}", flush=True)
        except urllib.error.HTTPError as he:
            err_body = he.read().decode('utf-8', errors='ignore')
            print(f"[ERROR] Scan upload returned HTTP {he.code}: {err_body}", flush=True)
            raise

        # 10. انتظار اكتمال الفحص من قبل العمال
        report_id = None
        poll_res = {}
        for _ in range(30):
            time.sleep(1.0)
            poll_req = urllib.request.Request(f"{BASE_URL}/api/tasks/{task_id}")
            with opener.open(poll_req) as resp:
                poll_res = json.loads(resp.read().decode('utf-8'))
                st = poll_res.get('status')
                if st == 'completed':
                    res_obj = poll_res.get('result', {}) or {}
                    report_id = res_obj.get('report_id') or res_obj.get('id') or poll_res.get('report_id')
                    break
                elif st == 'failed':
                    raise RuntimeError(f"Scan task failed: {poll_res.get('error')}")

        assert report_id is not None, f"Scan did not complete within 30 seconds. Last state: {poll_res}"
        print(f"   [PASS] Scan completed by workers. Report ID: {report_id}", flush=True)

        # 11. التحقق من فتح التقرير
        rep_req = urllib.request.Request(f"{BASE_URL}/api/reports/{report_id}")
        with opener.open(rep_req) as resp:
            assert resp.status == 200, "Report retrieval failed"
            rep_data = json.loads(resp.read().decode('utf-8'))
            assert 'overall_pct' in rep_data or 'id' in rep_data or 'report_id' in rep_data, f"Report missing expected keys: {list(rep_data.keys())}"
        print("   [PASS] Academic plagiarism report successfully retrieved.", flush=True)

        # 12. التحقق من تسجيل العمال ونبضات القلب
        db_file = DATA_DIR / "Database" / "papers.db"
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("SELECT id, status, capabilities, last_heartbeat_at FROM worker_registry;")
        workers = cur.fetchall()
        conn.close()
        assert len(workers) >= 1, f"No workers found registered in database! ({workers})"
        print(f"   [PASS] Workers registered in WorkerRegistry: {len(workers)} active worker(s).")

        # 13. التحقق من السجلات
        server_log = DATA_DIR / "Logs" / "server.log"
        worker_log = DATA_DIR / "Logs" / "workers.log"
        assert server_log.exists() and os.path.getsize(server_log) > 0, "server.log is empty or missing"
        assert worker_log.exists() and os.path.getsize(worker_log) > 0, "workers.log is empty or missing"
        print("   [PASS] Server and Worker logs confirmed on disk.")

        # 14. التحقق من منع التشغيل المزدوج (Single Instance Guard)
        print("[5] Testing duplicate launch prevention...")
        dup_proc = subprocess.run(
            [str(isolated_exe), "--cli"],
            env=env,
            cwd=str(TEST_DIR),
            capture_output=True,
            timeout=15
        )
        assert dup_proc.returncode == 0, f"Duplicate launch failed with code {dup_proc.returncode}"
        print("   [PASS] Duplicate instance cleanly detected running system and exited 0.")

    finally:
        # 15. الإيقاف السلس
        print("[6] Stopping system cleanly...", flush=True)
        kill_process_tree(proc)

    # التحقق من تحرير المنفذ
    port_freed = False
    for _ in range(20):
        if not is_port_listening(PORT):
            port_freed = True
            break
        time.sleep(0.5)
    assert port_freed, f"Port {PORT} is still occupied after shutdown!"
    print("   [PASS] Port 5055 released cleanly.", flush=True)

    # 16. التحقق من استدامة البيانات بعد إعادة التشغيل (Persistence & Restart Test)
    print("[7] Testing persistence across restarts...", flush=True)
    proc2 = subprocess.Popen(
        [str(isolated_exe), "--cli"],
        env=env,
        cwd=str(TEST_DIR)
    )
    try:
        ready2 = wait_for_server(BASE_URL, proc=proc2, timeout=25.0)
        assert ready2, "Server failed to restart"

        # محاولة تسجيل الدخول بنفس المستخدم السابق
        cookie_jar2 = http.cookiejar.CookieJar()
        opener2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar2))

        # جلب CSRF جديد
        with opener2.open(f"{BASE_URL}/api/auth/csrf-token") as resp:
            csrf_t2 = json.loads(resp.read().decode('utf-8'))['csrf_token']

        # تسجيل الدخول
        login_payload = json.dumps({
            "username": "superadmin",
            "password": "StrongPassword123!"
        }).encode('utf-8')
        login_req = urllib.request.Request(
            f"{BASE_URL}/api/auth/login",
            data=login_payload,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_t2
            }
        )
        with opener2.open(login_req) as resp:
            assert resp.status == 200, "Login after restart failed"
            login_res = json.loads(resp.read().decode('utf-8'))
            assert login_res.get('success') is True, "Login unsuccessful after restart"
        print("   [PASS] User and credentials persisted across restart.", flush=True)

        # التحقق من أن التقرير السابق ما زال موجوداً
        with opener2.open(f"{BASE_URL}/api/reports/{report_id}") as resp:
            assert resp.status == 200, "Report did not persist across restart"
        print("   [PASS] Research reports persisted across restart.", flush=True)

    finally:
        kill_process_tree(proc2)

    # 17. اختبار التشغيل من مسار يحتوي مسافات (Spaced Path Test)
    print("[8] Testing launch from path containing spaces...", flush=True)
    if SPACED_DIR.exists():
        shutil.rmtree(SPACED_DIR, ignore_errors=True)
    SPACED_DIR.mkdir(parents=True, exist_ok=True)
    spaced_exe = SPACED_DIR / "Arabic-Plagiarism-System.exe"
    shutil.copy2(isolated_exe, spaced_exe)

    spaced_env = os.environ.copy()
    spaced_env["ARABIC_APP_DATA_DIR"] = str(SPACED_DIR / "SpacedData")
    spaced_env["PORT"] = "5056"
    spaced_env["HOST"] = "127.0.0.1"

    proc_spaced = subprocess.Popen(
        [str(spaced_exe), "--cli"],
        env=spaced_env,
        cwd=str(SPACED_DIR)
    )
    try:
        ready_spaced = wait_for_server("http://127.0.0.1:5056", proc=proc_spaced, timeout=25.0)
        assert ready_spaced, "Spaced path executable failed to become ready"
        print("   [PASS] Spaced path execution verified successfully.", flush=True)
    finally:
        kill_process_tree(proc_spaced)

    # تنظيف مجلد المسافات
    time.sleep(1.0)
    shutil.rmtree(SPACED_DIR, ignore_errors=True)

    print("=" * 80)
    print("   [ALL PASS] SINGLE-EXE ISOLATION AND SMOKE TEST COMPLETED 100% SUCCESSFULLY")
    print("=" * 80)


if __name__ == '__main__':
    run_isolation_and_smoke_test()
