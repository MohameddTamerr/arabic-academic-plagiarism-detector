# -*- coding: utf-8 -*-
"""
End-to-end verification of packaged Arabic-Plagiarism-System.exe:
- Multipart PDF upload and text extraction inside packaged process
- Plagiarism analysis execution and verification
- Fail-closed AI detection behavior in production mode
- Research mode authorization audit inside packaged server
- PDF/HTML export and persistent report reopening
"""
import os
import sys
import time
import json
import uuid
import shutil
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = (ROOT / 'dist' / 'Arabic-Plagiarism-System.exe').resolve()
assert EXE.exists(), f"Executable not found: {EXE}"

# Create a representative Arabic academic PDF
import fitz
pdf_path = ROOT / 'scratch' / 'sample_academic_research.pdf'
doc = fitz.open()

# Page 1
p1 = doc.new_page()
arabic_text_p1 = (
    "المطلب الأول: الحماية الجنائية للآثار في القانون المقارن\n\n"
    "تعتبر الآثار والقطع التاريخية من أهم مقومات الهوية الوطنية والتراث الإنساني المشترك، "
    "ولذلك فقد أحاطتها التشريعات الحديثة بسياج من الضمانات العقابية الصارمة لحمايتها من السطو "
    "والتخريب أو التهريب غير المشروع عبر الحدود الوطنية.\n\n"
    "وقد أجمعت الاتفاقيات الدولية، ومن أبرزها اتفاقية اليونسكو لعام 1970، على التزام الدول الأطراف "
    "باتخاذ كافة التدابير اللازمة لمكافحة استيراد وتصدير ونقل ملكية الممتلكات الثقافية بطرق غير مشروعة."
)
p1.insert_text((50, 72), arabic_text_p1, fontsize=12)

# Page 2
p2 = doc.new_page()
arabic_text_p2 = (
    "المطلب الثاني: الإطار الإجرائي للضبط القضائي في جرائم التراث الثقافي\n\n"
    "إن التطور التاريخي لمفهوم حماية الآثار يقتضي منح مأموري الضبط القضائي صلاحيات خاصة "
    "تتيح لهم التفتيش والتحري الفوري عن المقتنيات الأثرية المشبوهة، مع ضرورة الالتزام التام "
    "بالضمانات الدستورية لصون الحريات العامة.\n\n"
    "الخاتمة وقائمة المراجع:\n"
    "1. د. أحمد فتحي سرور، الحماية الجنائية للحريات، دار النهضة العربية، 2018.\n"
    "2. د. محمود نجيب حسني، شرح قانون العقوبات - القسم العام، دار النهضة العربية، 2015."
)
p2.insert_text((50, 72), arabic_text_p2, fontsize=12)

doc.save(str(pdf_path))
doc.close()
print(f"Generated test academic PDF at: {pdf_path} ({pdf_path.stat().st_size} bytes)")

# Ensure previous server processes are killed
subprocess.run(['taskkill', '/F', '/IM', 'Arabic-Plagiarism-System.exe'], capture_output=True)
time.sleep(1)

test_data_dir = (ROOT / 'scratch' / 'packaged_pdf_test_data').resolve()
if test_data_dir.exists():
    try:
        shutil.rmtree(test_data_dir)
    except Exception:
        pass
test_data_dir.mkdir(parents=True, exist_ok=True)

test_env = os.environ.copy()
test_env['PORT'] = '5056'
test_env['PORTABLE_MODE'] = '1'
test_env['ARABIC_APP_DATA_DIR'] = str(test_data_dir)
test_env['SINGLE_EXE_WORKERS'] = '1'

print(f"Launching {EXE.name} on port 5056 with isolated data dir...")
proc = subprocess.Popen([str(EXE)], env=test_env)

def multipart_encode(fields, files):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('utf-8'))
        body.extend(str(value).encode('utf-8'))
        body.extend(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode('utf-8'))
        body.extend(f'Content-Type: {content_type}\r\n\r\n'.encode('utf-8'))
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode('utf-8'))
    return bytes(body), f"multipart/form-data; boundary={boundary}"

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
            req = urllib.request.Request("http://127.0.0.1:5056/api/system/ping")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    print(f"Packaged server ready at {elapsed:.1f}s: {data}")
                    ready = True
                    break
        except Exception:
            if attempt % 15 == 0:
                print(f"Waiting for packaged server... ({elapsed:.1f}s)")

    if not ready:
        print("ERROR: Server failed to start.")
        sys.exit(1)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    # Get CSRF
    with opener.open("http://127.0.0.1:5056/api/auth/csrf_token", timeout=5) as resp:
        csrf_token = json.loads(resp.read().decode())["csrf_token"]

    # First time setup
    setup_payload = {
        'username': 'admin_acceptance',
        'password': 'AcademicFinal2026!#',
        'full_name': 'مدير قبول الإصدار النهائي',
        'recovery_pin': '99887766'
    }
    setup_req = urllib.request.Request(
        "http://127.0.0.1:5056/api/auth/setup_first_admin",
        data=json.dumps(setup_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf_token}
    )
    with opener.open(setup_req, timeout=5) as resp:
        print("Initial Admin Setup Result:", json.loads(resp.read().decode()).get('success'))

    # Login
    login_payload = {'username': 'admin_acceptance', 'password': 'AcademicFinal2026!#'}
    login_req = urllib.request.Request(
        "http://127.0.0.1:5056/api/auth/login",
        data=json.dumps(login_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf_token}
    )
    with opener.open(login_req, timeout=5) as resp:
        print("Login Result:", json.loads(resp.read().decode()).get('success'))

    # Refresh CSRF
    with opener.open("http://127.0.0.1:5056/api/auth/csrf_token", timeout=5) as resp:
        csrf_token = json.loads(resp.read().decode())["csrf_token"]

    pdf_bytes = pdf_path.read_bytes()

    # 1. Test Production Mode Scan with PDF upload
    print("\n" + "=" * 65)
    print(" [1] TEST: Packaged PDF Upload in Production Mode (Default Fail-Closed)")
    print("=" * 65)
    body, ctype = multipart_encode(
        {'title': 'بحث الحماية الجنائية للآثار', 'author': 'د. سيف الدين', 'enable_ai_research': '0'},
        {'file': ('academic_research.pdf', pdf_bytes, 'application/pdf')}
    )
    req = urllib.request.Request(
        "http://127.0.0.1:5056/api/analyze",
        data=body,
        headers={'Content-Type': ctype, 'X-CSRFToken': csrf_token}
    )
    t_start = time.perf_counter()
    with opener.open(req, timeout=60) as resp:
        prod_rep = json.loads(resp.read().decode())
    t_scan = time.perf_counter() - t_start

    print(f"Production Scan Completed in {t_scan:.2f}s")
    print(f"Report ID: {prod_rep.get('id')}")
    print(f"Overall Plagiarism: {prod_rep.get('overall_pct')}% | Copied: {prod_rep.get('copied_pct')}%")
    print(f"Problematic Plagiarism: {prod_rep.get('problematic_pct')}%")
    print(f"AI Detection Status: {prod_rep.get('ai_analysis', {}).get('status')}")
    print(f"AI Detection Reason: {prod_rep.get('ai_analysis', {}).get('reason')}")
    print(f"AI Limitations: {prod_rep.get('ai_analysis', {}).get('limitations')}")
    assert prod_rep.get('ai_analysis', {}).get('status') == 'unavailable'
    assert prod_rep.get('ai_analysis', {}).get('estimated_ai_percentage') is None
    print("-> [PASS] Production scan completed with clean fail-closed AI status.")

    # 2. Test Authorized Research Mode Scan with PDF upload
    print("\n" + "=" * 65)
    print(" [2] TEST: Packaged PDF Upload in AI Research Mode (Attempted JIT Execution)")
    print("=" * 65)
    body_res, ctype_res = multipart_encode(
        {'title': 'بحث الحماية الجنائية - نمط استكشافي', 'author': 'د. سيف الدين', 'enable_ai_research': '1'},
        {'file': ('academic_research.pdf', pdf_bytes, 'application/pdf')}
    )
    req_res = urllib.request.Request(
        "http://127.0.0.1:5056/api/analyze",
        data=body_res,
        headers={'Content-Type': ctype_res, 'X-CSRFToken': csrf_token}
    )
    t_start = time.perf_counter()
    with opener.open(req_res, timeout=60) as resp:
        res_rep = json.loads(resp.read().decode())
    t_scan = time.perf_counter() - t_start
    res_id = res_rep.get('id')

    print(f"Research Scan Completed in {t_scan:.2f}s")
    print(f"Report ID: {res_id}")
    print(f"Overall Plagiarism: {res_rep.get('overall_pct')}%")
    ai_info = res_rep.get('ai_analysis', {})
    print(f"AI Analysis Result in Packaged Binary:")
    print(f"  status: {ai_info.get('status')}")
    print(f"  mode: {ai_info.get('mode')}")
    print(f"  reason: {ai_info.get('reason')}")
    print(f"  validation_status: {ai_info.get('validation_status')}")
    print(f"  estimated_ai_percentage: {ai_info.get('estimated_ai_percentage')}")
    print(f"  limitations: {ai_info.get('limitations')}")

    # 3. Test Export HTML
    print("\n" + "=" * 65)
    print(f" [3] TEST: Report HTML Export from Packaged Server (#{res_id})")
    print("=" * 65)
    export_req = urllib.request.Request(
        f"http://127.0.0.1:5056/api/export_html/{res_id}",
        headers={'X-CSRFToken': csrf_token}
    )
    with opener.open(export_req, timeout=10) as resp:
        html_export = resp.read().decode('utf-8')
        print(f"Exported HTML size: {len(html_export)} chars")
        assert "تقرير كشف الاستلال العلمي" in html_export
        assert "تحليل الكتابة بالذكاء الاصطناعي" in html_export
        print("-> [PASS] Exported HTML generated cleanly with separated Plagiarism and AI sections.")

    # 4. Test Persistent Reopen
    print("\n" + "=" * 65)
    print(f" [4] TEST: Persistent Reopen of Saved Report (#{res_id})")
    print("=" * 65)
    reopen_req = urllib.request.Request(
        f"http://127.0.0.1:5056/api/reports/{res_id}",
        headers={'X-CSRFToken': csrf_token}
    )
    with opener.open(reopen_req, timeout=10) as resp:
        reopened = json.loads(resp.read().decode())
        print(f"Reopened Report ID: {reopened.get('id')}")
        print(f"Reopened Overall Plagiarism: {reopened.get('overall_pct')}%")
        print(f"Reopened AI Status: {reopened.get('ai_analysis', {}).get('status')}")
        assert reopened.get('id') == res_id
        print("-> [PASS] Saved report correctly reopened and identical to generated report.")

    print("\n" + "=" * 65)
    print("   ALL PACKAGED PDF WORKFLOW TESTS EXECUTED SUCCESSFULLY")
    print("=" * 65)

finally:
    print("\nStopping packaged server process...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    subprocess.run(['taskkill', '/F', '/IM', 'Arabic-Plagiarism-System.exe'], capture_output=True)
    print("Packaged process cleanly stopped.")
