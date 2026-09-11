# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_binaries, collect_all

# ─── numpy: يجب تضمين الـ .pyd binaries صراحةً وإلا تفشل الـ C-extensions ────
numpy_datas,    numpy_binaries,    numpy_hidden    = collect_all('numpy')
scipy_datas,    scipy_binaries,    scipy_hidden    = collect_all('scipy')
sklearn_datas,  sklearn_binaries,  sklearn_hidden  = collect_all('sklearn')

hiddenimports = [
    'waitress', 'waitress.server', 'waitress.compat', 'waitress.adjustments',
    'waitress.buffers', 'waitress.channel', 'waitress.receiver', 'waitress.rfc7230',
    'waitress.task', 'waitress.utilities', 'waitress.wasyncore',
    'sqlalchemy.dialects.sqlite', 'sqlalchemy.dialects.sqlite.pysqlite',
    'bcrypt', '_bcrypt', 'jwt', 'tkinter', 'tkinter.ttk',
    'tkinter.messagebox', 'tkinter.scrolledtext',
    'numpy', 'numpy.core', 'numpy.core._multiarray_umath',
    'numpy.core._multiarray_tests', 'numpy.core.multiarray',
    'numpy.core.umath', 'numpy.lib', 'numpy.fft', 'numpy.linalg',
    'numpy.random', 'numpy.random._common', 'numpy.random.bit_generator',
    'sklearn', 'sklearn.feature_extraction', 'sklearn.feature_extraction.text',
    'scipy', 'scipy.sparse', 'scipy.special._cdflib',
    'docx', 'pdfplumber', 'pypdf', 'reportlab', 'reportlab.lib',
    'reportlab.pdfgen', 'reportlab.platypus',
    'psutil', 'cffi', '_cffi_backend',
    'app', 'app.wsgi_server', 'app.single_exe', 'app.single_exe.entrypoint',
    'app.single_exe.app_controller', 'app.single_exe.worker_runner',
    'app.single_exe.gui_controller', 'app.single_exe.tray_controller',
    'win32gui', 'win32con', 'win32api',
    'argon2', 'argon2.low_level', 'argon2_cffi_bindings', '_argon2_cffi_bindings',
    'qrcode', 'qrcode.image', 'qrcode.image.pil',
    'cv2', 'PIL', 'PIL.Image',
    'app.services.recovery_service', 'app.routes.recovery_routes',
    'app.routes.common_phrases_routes',
    'app.utils', 'app.utils.windows_security',
    'config', 'plagiarism_detector',
]
hiddenimports += numpy_hidden
hiddenimports += scipy_hidden
hiddenimports += sklearn_hidden
hiddenimports += collect_submodules('numpy')
hiddenimports += collect_submodules('scipy')
hiddenimports += collect_submodules('sklearn')


a = Analysis(
    ['C:\\Users\\user\\Downloads\\Baba\\app\\single_exe\\entrypoint.py'],
    pathex=['C:\\Users\\user\\Downloads\\Baba', 'C:\\Users\\user\\Downloads\\Baba\\vendor'],
    binaries=[] + numpy_binaries + scipy_binaries + sklearn_binaries,
    datas=[
        ('C:\\Users\\user\\Downloads\\Baba\\templates', 'templates'),
        ('C:\\Users\\user\\Downloads\\Baba\\static', 'static'),
        ('C:\\Users\\user\\Downloads\\Baba\\assets\\tessdata', 'tessdata'),
        ('C:\\Users\\user\\Downloads\\Baba\\Police-Academy-College-of-Graduate-Studies.png', '.'),
        ('C:\\Users\\user\\Downloads\\Baba\\release_manifest.json', '.'),
    ] + numpy_datas + scipy_datas + sklearn_datas,
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
