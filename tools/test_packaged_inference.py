# -*- coding: utf-8 -*-
"""
Test packaged AI inference against the real dist/Arabic-Plagiarism-System.exe
in an isolated temporary data directory.
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
exe = (ROOT / 'dist' / 'Arabic-Plagiarism-System.exe').resolve()
assert exe.exists(), f"EXE not found: {exe}"

# Terminate existing
subprocess.run(['taskkill', '/F', '/IM', 'Arabic-Plagiarism-System.exe'], capture_output=True)
time.sleep(1)

test_data_dir = (ROOT / 'scratch' / 'packaged_test_data').resolve()
if test_data_dir.exists():
    import shutil
    try:
        shutil.rmtree(test_data_dir)
    except Exception:
        pass
test_data_dir.mkdir(parents=True, exist_ok=True)

test_env = os.environ.copy()
test_env['PORT'] = '5055'
test_env['PORTABLE_MODE'] = '1'
test_env['ARABIC_APP_DATA_DIR'] = str(test_data_dir)
test_env['SINGLE_EXE_WORKERS'] = '1'

print(f"Launching {exe.name} on port 5055 with data dir {test_data_dir}...")
proc = subprocess.Popen([str(exe)], env=test_env)

t0 = time.time()
ready = False
try:
    for attempt in range(120):
        time.sleep(1)
        elapsed = time.time() - t0
        ret = proc.poll()
        if ret is not None:
            print(f"Process terminated with exit code {ret} at {elapsed:.1f}s")
            break
        try:
            req = urllib.request.Request("http://127.0.0.1:5055/api/system/ping")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    print(f"Server is ready at {elapsed:.1f}s: {data}")
                    ready = True
                    break
        except Exception:
            if attempt % 15 == 0:
                print(f"Waiting for server... ({elapsed:.1f}s)")

    if not ready:
        print("ERROR: Server failed to start within timeout.")
        sys.exit(1)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    # Get CSRF Token
    with opener.open("http://127.0.0.1:5055/api/auth/csrf_token", timeout=5) as resp:
        csrf_data = json.loads(resp.read().decode())
        csrf_token = csrf_data.get("csrf_token")
        print("Obtained CSRF Token:", csrf_token[:12], "...")

    # Check Auth status
    with opener.open("http://127.0.0.1:5055/api/auth/status", timeout=5) as resp:
        auth_status = json.loads(resp.read().decode())
        print("Auth status:", auth_status)

    if auth_status.get("needs_first_time_setup") or auth_status.get("setup_required"):
        print("Setting up initial superadmin...")
        setup_payload = {
            'username': 'admin_test',
            'password': 'AcademicSecure2026!#',
            'full_name': 'مسؤول الاختبار الأكاديمي',
            'recovery_pin': '87654321'
        }
        setup_req = urllib.request.Request(
            "http://127.0.0.1:5055/api/auth/setup_first_admin",
            data=json.dumps(setup_payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf_token
            }
        )
        with opener.open(setup_req, timeout=5) as resp:
            setup_res = json.loads(resp.read().decode())
            print("Setup response:", setup_res.get('status') or setup_res.get('success'))

    # Login to authenticate session
    print("Logging in as admin_test...")
    login_payload = {
        'username': 'admin_test',
        'password': 'AcademicSecure2026!#'
    }
    login_req = urllib.request.Request(
        "http://127.0.0.1:5055/api/auth/login",
        data=json.dumps(login_payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf_token
        }
    )
    with opener.open(login_req, timeout=5) as resp:
        login_res = json.loads(resp.read().decode())
        print("Login success:", login_res.get('success'), "| Message:", login_res.get('message'))

    # Refresh CSRF token after login (rotate_csrf_token happens upon login)
    with opener.open("http://127.0.0.1:5055/api/auth/csrf_token", timeout=5) as resp:
        csrf_data = json.loads(resp.read().decode())
        csrf_token = csrf_data.get("csrf_token")
        print("Post-login fresh CSRF Token:", csrf_token[:12], "...")

    # Verify session profile
    with opener.open("http://127.0.0.1:5055/api/auth/me", timeout=5) as resp:
        me = json.loads(resp.read().decode())
        curr_user = me.get('user') or {}
        print("Current User Profile:", curr_user.get('username'), "| Role:", curr_user.get('role'))

    sample_text = (
        "تعتبر حماية الآثار والتحف القديمة من أهم الواجبات القانونية التي تقع على عاتق الدولة "
        "للحفاظ على التراث الثقافي والتاريخي للأمة، وقد نص المشرع على عقوبات رادعة لكل من تسول "
        "له نفسه سرقة أو تهريب تلك المقتنيات.\n\n"
        "إن التطور التاريخي لمفهوم حقوق الإنسان يؤكد أن العدالة والمساواة بين الأفراد ليست وليدة "
        "العصر الحديث، بل هي نتاج تراكمي عبر الحضارات الإنسانية المتتابعة والتي أكدت على كرامة النفس البشرية."
    )

    # 1. Test Production Mode Scan (Default Fail-Closed)
    print("\n=======================================================")
    print("   TEST 1: Packaged EXE in Production Mode (Default)")
    print("=======================================================")
    prod_data = urllib.parse.urlencode({
        'text': sample_text,
        'title': 'بحث إنتاجي اختباري',
        'enable_ai_research': '0'
    }).encode('utf-8')
    req = urllib.request.Request(
        "http://127.0.0.1:5055/api/analyze",
        data=prod_data,
        headers={'X-CSRFToken': csrf_token}
    )
    with opener.open(req, timeout=30) as resp:
        prod_report = json.loads(resp.read().decode())
        print("Report ID:", prod_report.get('id'))
        print("Plagiarism overall pct:", prod_report.get('overall_pct'))
        print("Copied pct:", prod_report.get('copied_pct'))
        print("Paraphrase pct:", prod_report.get('paraphrase_pct'))
        ai_prod = prod_report.get('ai_analysis', {})
        print("AI status:", ai_prod.get('status'))
        print("AI reason:", ai_prod.get('reason'))
        print("AI validation_status:", ai_prod.get('validation_status'))
        print("AI limitations:", ai_prod.get('limitations'))
        assert ai_prod.get('status') == 'unavailable', "Production mode must be fail-closed (unavailable)"
        assert ai_prod.get('estimated_ai_percentage') is None, "AI percentage must NOT be fabricated"
        print("-> [PASS] Production mode correctly fail-closed with zero fabricated percentages.")

    # 2. Test Authorized Research Mode Scan
    print("\n=======================================================")
    print("   TEST 2: Packaged EXE in Authorized Research Mode")
    print("=======================================================")
    res_data = urllib.parse.urlencode({
        'text': sample_text,
        'title': 'بحث نمط استكشافي تجريبي',
        'enable_ai_research': '1'
    }).encode('utf-8')
    req = urllib.request.Request(
        "http://127.0.0.1:5055/api/analyze",
        data=res_data,
        headers={'X-CSRFToken': csrf_token}
    )
    with opener.open(req, timeout=60) as resp:
        res_report = json.loads(resp.read().decode())
        rep_id = res_report.get('id')
        print("Report ID:", rep_id)
        print("Plagiarism overall pct:", res_report.get('overall_pct'))
        ai_res = res_report.get('ai_analysis', {})
        print("AI status:", ai_res.get('status'))
        print("AI mode:", ai_res.get('mode'))
        print("AI model:", ai_res.get('model'))
        print("AI estimated percentage:", ai_res.get('estimated_ai_percentage'))
        print("AI human percentage:", ai_res.get('estimated_human_percentage'))
        print("AI uncertain percentage:", ai_res.get('uncertain_percentage'))
        print("AI paragraphs count:", ai_res.get('paragraphs_count'))
        print("AI limitations / warning:", ai_res.get('limitations'))
        paras = ai_res.get('paragraphs', [])
        if paras:
            print("First paragraph classification:", paras[0].get('classification'), "| Prob:", paras[0].get('ai_probability'))

    # 3. Test Persistence and Reopening
    print("\n=======================================================")
    print(f"   TEST 3: Reopening Persisted Report from API ({rep_id})")
    print("=======================================================")
    with opener.open(f"http://127.0.0.1:5055/api/reports/{rep_id}", timeout=5) as resp:
        reopened = json.loads(resp.read().decode())
        print("Reopened report ID:", reopened.get('id'))
        print("Reopened Plagiarism overall pct:", reopened.get('overall_pct'))
        print("Reopened AI status:", reopened.get('ai_analysis', {}).get('status'))
        print("Reopened AI mode:", reopened.get('ai_analysis', {}).get('mode'))
        print("Reopened AI estimated pct:", reopened.get('ai_analysis', {}).get('estimated_ai_percentage'))

finally:
    print("\nTerminating packaged test process...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    subprocess.run(['taskkill', '/F', '/IM', 'Arabic-Plagiarism-System.exe'], capture_output=True)
    print("Test finished successfully.")
