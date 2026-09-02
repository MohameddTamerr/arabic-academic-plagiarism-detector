# -*- coding: utf-8 -*-
import sys, os, subprocess, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print("=" * 60)
print("   كاشف الانتحال العربي - أداة البناء")
print("=" * 60)

print("\n[1/3] تثبيت مكتبات البناء (PyInstaller, Flask)...")
subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "flask", "scikit-learn", "numpy", "pdfplumber", "python-docx", "--quiet"], check=True)

print("\n[2/3] جاري بناء ملف الـ .exe لتصميم الواجهة الجديد (قد يستغرق دقيقة أو دقيقتين)...")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", "ArabicPlagiarismDetector",
    "--add-data", "templates;templates",
    "--exclude-module", "PyQt5",
    "--exclude-module", "PyQt6",
    "--exclude-module", "PySide2",
    "--exclude-module", "PySide6",
    "--exclude-module", "matplotlib",
    "--exclude-module", "torch",
    "--exclude-module", "IPython",
    "--hidden-import", "sklearn.feature_extraction.text",
    "--hidden-import", "sklearn.metrics.pairwise",
    "--hidden-import", "pdfplumber",
    "--hidden-import", "docx",
    "--hidden-import", "flask",
    "run_app.py"
]
result = subprocess.run(cmd)

if result.returncode == 0:
    print("\n" + "=" * 60)
    print("[3/3] تم البناء بنجاح!")
    exe_path = os.path.join("dist", "ArabicPlagiarismDetector.exe")
    print(f"الملف الجاهز موجود في: {os.path.abspath(exe_path)}")
    print("انقله بفلاشة USB للجهاز الهدف - يعمل بدون إنترنت")
    print("=" * 60)
else:
    print("\n[خطأ] حدثت مشكلة أثناء بناء الـ exe.")

input("\nاضغط Enter للإغلاق...")
