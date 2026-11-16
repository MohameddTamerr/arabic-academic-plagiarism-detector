# -*- coding: utf-8 -*-
import subprocess
import os
import time
import glob
from pathlib import Path

# Run dist/Arabic-Plagiarism-System.exe --help or run briefly and check the latest created _MEI folder
existing_meis = set(glob.glob(os.path.join(os.environ['TEMP'], '_MEI*')))

proc = subprocess.Popen([r'dist\Arabic-Plagiarism-System.exe'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(4)

# Find new _MEI directory
new_meis = set(glob.glob(os.path.join(os.environ['TEMP'], '_MEI*'))) - existing_meis
print("New _MEI directory created:", new_meis)

if new_meis:
    mei_dir = list(new_meis)[0]
    tmpl = Path(mei_dir) / 'templates' / 'index.html'
    if tmpl.exists():
        content = tmpl.read_text(encoding='utf-8', errors='ignore')
        print("Template length inside EXE:", len(content))
        print("Has ocr-btn-accurate (Upload enhancement):", 'ocr-btn-accurate' in content)
        print("Has login-brand-header-center (Login redesign):", 'login-brand-header-center' in content)
        print("Has clamp(400px, 32.5vw, 640px) (Login scaling):", 'clamp(400px, 32.5vw, 640px)' in content)
        print("Has hero-title-accent-bar (Gold accent):", 'hero-title-accent-bar' in content)
        print("Has togglePasswordVisibility:", 'togglePasswordVisibility' in content)

proc.terminate()
try:
    proc.wait(timeout=2)
except Exception:
    proc.kill()
