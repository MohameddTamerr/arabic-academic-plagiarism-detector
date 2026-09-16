# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_all

# numpy C-extensions fix
numpy_datas,   numpy_binaries,   numpy_hidden   = collect_all('numpy')
scipy_datas,   scipy_binaries,   scipy_hidden   = collect_all('scipy')
sklearn_datas, sklearn_binaries, sklearn_hidden = collect_all('sklearn')

hiddenimports = [
    'waitress', 'waitress.server', 'waitress.compat', 'waitress.adjustments',
    'waitress.buffers', 'waitress.channel', 'waitress.receiver', 'waitress.rfc7230',
    'waitress.task', 'waitress.utilities', 'waitress.wasyncore',
    'sqlalchemy.dialects.sqlite', 'sqlalchemy.dialects.sqlite.pysqlite',
    'bcrypt', '_bcrypt', 'jwt', 'tkinter', 'tkinter.ttk',
    'tkinter.messagebox', 'tkinter.scrolledtext',
    'numpy', 'numpy.core', 'numpy.core._multiarray_umath',
    'numpy.core.multiarray', 'numpy.core.umath',
    'numpy.lib', 'numpy.fft', 'numpy.linalg', 'numpy.random',
    'sklearn', 'sklearn.feature_extraction', 'sklearn.feature_extraction.text',
    'scipy', 'scipy.sparse', 'scipy.special._cdflib',
    'docx', 'pdfplumber', 'pypdf', 'reportlab', 'reportlab.lib',
    'reportlab.pdfgen', 'reportlab.platypus',
    'psutil', 'cffi', '_cffi_backend',
    'app', 'app.wsgi_server', 'app.single_exe', 'app.single_exe.entrypoint',
    'app.single_exe.app_controller', 'app.single_exe.worker_runner',
    'app.single_exe.gui_controller',
    'app.routes.common_phrases_routes',
    'config', 'plagiarism_detector',
]
hiddenimports += numpy_hidden + scipy_hidden + sklearn_hidden
hiddenimports += collect_submodules('numpy')
hiddenimports += collect_submodules('scipy')
hiddenimports += collect_submodules('sklearn')


a = Analysis(
    ['app\\single_exe\\entrypoint.py'],
    pathex=['.', 'vendor'],
    binaries=[] + numpy_binaries + scipy_binaries + sklearn_binaries,
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('Police-Academy-College-of-Graduate-Studies.png', '.'),
        ('release_manifest.json', '.'),
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
)

