# -*- coding: utf-8 -*-
"""
أداة بناء وتجميع الحزمة التنفيذية الموحدة لنظام فحص الاستلال الأكاديمي:
Arabic-Plagiarism-System.exe
- تستخدم PyInstaller 6.x لبناء ملف تنفيذي وحيد قائم بذاته تماماً.
- تدمج كافة المكتبات المطلوبة وخادم Waitress وقوالب الواجهة والأصول الثابتة والأيقونة الرسمية.
- تضمن عدم الاعتماد على بايثون مثبت في النظام أو مجلد Runtime خارجي.
"""

import os
import sys
import time
import hashlib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT_DIR / "vendor"
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
TESSDATA_DIR = ROOT_DIR / "assets" / "tessdata"
LOGO_FILE = ROOT_DIR / "Police-Academy-College-of-Graduate-Studies.png"
MANIFEST_FILE = ROOT_DIR / "release_manifest.json"
SKLEARN_REPR_ASSETS_DIR = VENDOR_DIR / "sklearn" / "utils" / "_repr_html"
ICON_FILE = ROOT_DIR / "scratch" / "app.ico"
ENTRY_POINT = ROOT_DIR / "app" / "single_exe" / "entrypoint.py"
DIST_DIR = ROOT_DIR / "dist"
VENDOR_RUNTIME_DIRS = (
    (VENDOR_DIR / "numpy.libs", "numpy.libs"),
    (VENDOR_DIR / "scipy.libs", "scipy.libs"),
    (VENDOR_DIR / "sklearn" / ".libs", r"sklearn\.libs"),
)

# إضافة vendor للجلسة الحالية
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import PyInstaller.__main__


def build_single_exe():
    print("=" * 75)
    print("   BUILDING SINGLE-EXE: Arabic-Plagiarism-System.exe")
    print("=" * 75)
    t0 = time.perf_counter()

    required_ocr_models = [TESSDATA_DIR / 'ara.traineddata', TESSDATA_DIR / 'eng.traineddata']
    missing_ocr_models = [str(path) for path in required_ocr_models if not path.is_file()]
    if missing_ocr_models:
        raise FileNotFoundError(f"Missing bundled OCR models: {missing_ocr_models}")

    vendor_runtime_binaries = []
    for library_dir, destination in VENDOR_RUNTIME_DIRS:
        dlls = sorted(library_dir.glob("*.dll"))
        if not dlls:
            raise FileNotFoundError(f"Missing vendored runtime DLLs: {library_dir}")
        vendor_runtime_binaries.extend(
            f"--add-binary={dll_path};{destination}" for dll_path in dlls
        )

    args = [
        str(ENTRY_POINT),
        "--name=Arabic-Plagiarism-System",
        "--onefile",
        "--noconsole",
        f"--icon={ICON_FILE}",
        "--clean",
        f"--distpath={DIST_DIR}",
        f"--paths={ROOT_DIR}",
        f"--paths={VENDOR_DIR}",
        f"--add-data={TEMPLATES_DIR};templates",
        f"--add-data={STATIC_DIR};static",
        f"--add-data={TESSDATA_DIR};tessdata",
        f"--add-data={LOGO_FILE};.",
        f"--add-data={MANIFEST_FILE};.",
        f"--add-data={SKLEARN_REPR_ASSETS_DIR};sklearn/utils/_repr_html",
        # Hidden imports
        "--hidden-import=waitress",
        "--hidden-import=waitress.server",
        "--hidden-import=waitress.compat",
        "--hidden-import=waitress.adjustments",
        "--hidden-import=waitress.buffers",
        "--hidden-import=waitress.channel",
        "--hidden-import=waitress.receiver",
        "--hidden-import=waitress.rfc7230",
        "--hidden-import=waitress.task",
        "--hidden-import=waitress.utilities",
        "--hidden-import=waitress.wasyncore",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=sqlalchemy.dialects.sqlite.pysqlite",
        "--hidden-import=bcrypt",
        "--hidden-import=_bcrypt",
        "--hidden-import=jwt",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.scrolledtext",
        "--hidden-import=sklearn",
        "--hidden-import=sklearn._cyutility",
        "--hidden-import=sklearn._isotonic",
        "--hidden-import=sklearn.feature_extraction",
        "--hidden-import=sklearn.feature_extraction.text",
        "--hidden-import=scipy",
        "--hidden-import=scipy._cyutility",
        "--hidden-import=scipy.sparse",
        "--hidden-import=scipy.special._cdflib",
        "--hidden-import=scipy._external.array_api_compat.numpy",
        "--hidden-import=scipy._external.array_api_compat.numpy.fft",
        "--hidden-import=scipy._external.array_api_compat.numpy.linalg",
        "--hidden-import=scipy._external.array_api_compat.numpy._aliases",
        "--hidden-import=scipy._external.array_api_compat.numpy._info",
        "--hidden-import=scipy._external.array_api_compat.numpy._typing",
        "--hidden-import=scipy._external.array_api_compat.common",
        "--hidden-import=scipy._external.array_api_compat.common._aliases",
        "--hidden-import=scipy._external.array_api_compat.common._fft",
        "--hidden-import=scipy._external.array_api_compat.common._helpers",
        "--hidden-import=scipy._external.array_api_compat.common._linalg",
        "--hidden-import=scipy._external.array_api_compat.common._typing",
        "--collect-submodules=scipy._external.array_api_compat.numpy",
        "--collect-submodules=scipy._external.array_api_compat.common",
        "--collect-all=numpy",
        "--hidden-import=numpy",
        "--hidden-import=numpy._core",
        "--hidden-import=numpy._core._exceptions",
        "--hidden-import=docx",
        "--hidden-import=pdfplumber",
        "--hidden-import=pypdf",
        "--hidden-import=reportlab",
        "--hidden-import=reportlab.lib",
        "--hidden-import=reportlab.pdfgen",
        "--hidden-import=reportlab.platypus",
        "--hidden-import=psutil",
        "--hidden-import=cffi",
        "--hidden-import=_cffi_backend",
        "--hidden-import=app",
        "--hidden-import=app.wsgi_server",
        "--hidden-import=app.single_exe",
        "--hidden-import=app.single_exe.entrypoint",
        "--hidden-import=app.single_exe.app_controller",
        "--hidden-import=app.single_exe.worker_runner",
        "--hidden-import=app.single_exe.gui_controller",
        "--hidden-import=app.single_exe.tray_controller",
        "--hidden-import=win32gui",
        "--hidden-import=win32con",
        "--hidden-import=win32api",
        "--hidden-import=argon2",
        "--hidden-import=argon2.low_level",
        "--hidden-import=argon2_cffi_bindings",
        "--hidden-import=_argon2_cffi_bindings",
        "--hidden-import=qrcode",
        "--hidden-import=qrcode.image",
        "--hidden-import=qrcode.image.pil",
        "--hidden-import=cv2",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=app.services.recovery_service",
        "--hidden-import=app.routes.recovery_routes",
        "--hidden-import=app.utils",
        "--hidden-import=app.utils.windows_security",
        "--hidden-import=config",
        "--hidden-import=plagiarism_detector",

        # Excludes
        "--exclude-module=torch",
        "--exclude-module=torchvision",
        "--exclude-module=torchaudio",
        "--exclude-module=tensorflow",
        "--exclude-module=matplotlib",
        "--exclude-module=PyQt5",
        "--exclude-module=PyQt6",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "-y"
    ]

    # Keep native extension modules and their hashed runtime DLLs from the same
    # vendored NumPy/SciPy/scikit-learn release. Mixing them causes the frozen
    # application to fail while importing NumPy C-extensions at startup.
    args.extend(vendor_runtime_binaries)

    print("Executing PyInstaller compiler...")
    PyInstaller.__main__.run(args)
    t1 = time.perf_counter()

    exe_path = DIST_DIR / "Arabic-Plagiarism-System.exe"
    if not exe_path.exists():
        print("[CRITICAL ERROR] Target executable was not generated!")
        sys.exit(1)

    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    with open(exe_path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    print("=" * 75)
    print("   [OK] SINGLE-EXE BUILD COMPLETED SUCCESSFULLY")
    print("=" * 75)
    print(f"File Path:   {exe_path}")
    print(f"Size:        {size_mb:.2f} MB ({os.path.getsize(exe_path):,} bytes)")
    print(f"SHA-256:     {sha256}")
    print(f"Build Time:  {t1 - t0:.2f} seconds")
    print("=" * 75)
    return str(exe_path)


if __name__ == '__main__':
    build_single_exe()
