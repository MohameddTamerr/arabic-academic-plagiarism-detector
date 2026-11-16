# -*- coding: utf-8 -*-
import hashlib
from PyInstaller.archive.readers import CArchiveReader

reader = CArchiveReader('dist/Arabic-Plagiarism-System.exe')
entry_name = 'templates\\index.html'

data = reader.extract(entry_name)[1]
sha = hashlib.sha256(data).hexdigest()

with open('templates/index.html', 'rb') as f:
    src_data = f.read()
    src_sha = hashlib.sha256(src_data).hexdigest()

print("="*65)
print("     FORENSIC EXECUTABLE TEMPLATE VERIFICATION RESULTS")
print("="*65)
print(f"Packaged Template Size : {len(data):,} bytes")
print(f"Packaged Template SHA  : {sha}")
print(f"Source Template SHA    : {src_sha}")
print(f"Byte-for-byte Match    : {'YES (100% IDENTICAL)' if sha == src_sha else 'NO (MISMATCH)'}")
print(f"Has .dash-banner       : {b'dash-banner' in data}")
print(f"Has Subtitle           : {'نظرة عامة على عمليات الفحص والأبحاث والتقارير'.encode('utf-8') in data}")
print(f"Has KPI 3 Cards Grid   : {b'dash-kpis-container' in data}")
print(f"Has Recent Activity    : {b'dash-recent-activity-list' in data}")
print(f"Has System Status      : {'حالة مكونات النظام'.encode('utf-8') in data}")
print("="*65)
