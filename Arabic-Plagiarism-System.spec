# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\user\\Downloads\\Baba\\templates', 'templates'), ('C:\\Users\\user\\Downloads\\Baba\\static', 'static'), ('C:\\Users\\user\\Downloads\\Baba\\assets\\tessdata', 'tessdata'), ('C:\\Users\\user\\Downloads\\Baba\\Police-Academy-College-of-Graduate-Studies.png', '.'), ('C:\\Users\\user\\Downloads\\Baba\\release_manifest.json', '.'), ('C:\\Users\\user\\Downloads\\Baba\\vendor\\sklearn\\utils\\_repr_html', 'sklearn/utils/_repr_html')]
binaries = [('C:\\Users\\user\\Downloads\\Baba\\vendor\\numpy.libs\\libscipy_openblas64_-327b2e0bcffce2882e0dc04cdeb4eaa6.dll', 'numpy.libs'), ('C:\\Users\\user\\Downloads\\Baba\\vendor\\numpy.libs\\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll', 'numpy.libs'), ('C:\\Users\\user\\Downloads\\Baba\\vendor\\scipy.libs\\libscipy_openblas-197ee2fc9b4d071f7e048078cac74115.dll', 'scipy.libs'), ('C:\\Users\\user\\Downloads\\Baba\\vendor\\sklearn\\.libs\\msvcp140.dll', 'sklearn\\.libs'), ('C:\\Users\\user\\Downloads\\Baba\\vendor\\sklearn\\.libs\\vcomp140.dll', 'sklearn\\.libs')]
hiddenimports = ['waitress', 'waitress.server', 'waitress.compat', 'waitress.adjustments', 'waitress.buffers', 'waitress.channel', 'waitress.receiver', 'waitress.rfc7230', 'waitress.task', 'waitress.utilities', 'waitress.wasyncore', 'sqlalchemy.dialects.sqlite', 'sqlalchemy.dialects.sqlite.pysqlite', 'bcrypt', '_bcrypt', 'jwt', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.scrolledtext', 'sklearn', 'sklearn._cyutility', 'sklearn._isotonic', 'sklearn.feature_extraction', 'sklearn.feature_extraction.text', 'scipy', 'scipy._cyutility', 'scipy.sparse', 'scipy.special._cdflib', 'scipy._external.array_api_compat.numpy', 'scipy._external.array_api_compat.numpy.fft', 'scipy._external.array_api_compat.numpy.linalg', 'scipy._external.array_api_compat.numpy._aliases', 'scipy._external.array_api_compat.numpy._info', 'scipy._external.array_api_compat.numpy._typing', 'scipy._external.array_api_compat.common', 'scipy._external.array_api_compat.common._aliases', 'scipy._external.array_api_compat.common._fft', 'scipy._external.array_api_compat.common._helpers', 'scipy._external.array_api_compat.common._linalg', 'scipy._external.array_api_compat.common._typing', 'numpy', 'numpy._core', 'numpy._core._exceptions', 'docx', 'pdfplumber', 'pypdf', 'reportlab', 'reportlab.lib', 'reportlab.pdfgen', 'reportlab.platypus', 'psutil', 'cffi', '_cffi_backend', 'app', 'app.wsgi_server', 'app.single_exe', 'app.single_exe.entrypoint', 'app.single_exe.app_controller', 'app.single_exe.worker_runner', 'app.single_exe.gui_controller', 'app.single_exe.tray_controller', 'win32gui', 'win32con', 'win32api', 'argon2', 'argon2.low_level', 'argon2_cffi_bindings', '_argon2_cffi_bindings', 'qrcode', 'qrcode.image', 'qrcode.image.pil', 'cv2', 'PIL', 'PIL.Image', 'app.services.recovery_service', 'app.routes.recovery_routes', 'app.utils', 'app.utils.windows_security', 'config', 'plagiarism_detector']
hiddenimports += collect_submodules('scipy._external.array_api_compat.numpy')
hiddenimports += collect_submodules('scipy._external.array_api_compat.common')
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\user\\Downloads\\Baba\\app\\single_exe\\entrypoint.py'],
    pathex=['C:\\Users\\user\\Downloads\\Baba', 'C:\\Users\\user\\Downloads\\Baba\\vendor'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'tensorflow', 'matplotlib', 'PyQt5', 'PyQt6', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Arabic-Plagiarism-System',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\user\\Downloads\\Baba\\scratch\\app.ico'],
)
