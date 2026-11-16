# -*- coding: utf-8 -*-
"""
نقطة الدخول المركزية للملف التنفيذي الموحد (Single-EXE Application Entrypoint):
- تتولى freeze_support() لمنع تكرار النوافذ أو العمليات في ويندوز.
- توجه وسائط سطر الأوامر (--worker، --cli، إلخ).
- تشغل خادم الإنتاج والعمال بصمت في الخلفية مع فتح المتصفح للمستخدم وتثبيت أيقونة شريط المهام.
"""

import os
import sys
import time
import signal
import multiprocessing
import traceback
from datetime import datetime
from pathlib import Path


def _write_early_startup_error(exc_type, exc_value, exc_traceback):
    """Persist import-time failures that occur before AppController is created."""
    try:
        fallback_root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ArabicAcademicPlagiarismSystem' / 'Data'
        data_root = Path(os.environ.get('ARABIC_APP_DATA_DIR', fallback_root))
        log_dir = data_root / 'Logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / 'early_startup_crash.log', 'w', encoding='utf-8') as crash_log:
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=crash_log)
    except Exception:
        pass

    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _write_early_startup_error

# إعادة تهيئة الترميز على ويندوز لدعم العربية والرموز
if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# حماية مخارج النظام في نمط النوافذ دون كونسول
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# 1. دعم تجميد العمليات المتعددة في ويندوز (إلزامي كأول استدعاء)
multiprocessing.freeze_support()

# 2. فحص ما إذا كانت العملية استدعاءً لعامل فحص داخلي
if '--worker' in sys.argv:
    w_idx = sys.argv.index('--worker')
    worker_args = [arg for i, arg in enumerate(sys.argv) if i != w_idx and i > 0]
    from app.single_exe.worker_runner import run_frozen_worker
    run_frozen_worker(worker_args)
    sys.exit(0)

# إضافة مسار المشروع ومجلد vendor إن وجدا مبكراً لضمان توفر المكتبات
root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

vendor_path = os.path.join(root_path, 'vendor')
if os.path.exists(vendor_path) and vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

bundle_path = getattr(sys, '_MEIPASS', None)
if bundle_path and bundle_path not in sys.path:
    sys.path.insert(0, bundle_path)

# 3. دعم استرجاع وتعيين حساب مدير النظام بطريقة آمنة ومشروطة بصلاحيات مسؤول ويندوز
if any(arg in sys.argv for arg in ['--reset-admin', '--admin-reset', '--recover-admin', '--reset-password']):
    import ctypes
    from app.security.emergency_recovery import (
        is_windows_admin,
        perform_emergency_admin_reset,
        validate_new_recovery_password
    )

    try:
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
            sys.stderr = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
    except Exception:
        pass

    # 1. اشتراط صلاحيات مسؤول نظام التشغيل Windows المرتفعة
    bypass_elevation = ('--bypass-elevation-for-test' in sys.argv)
    if not bypass_elevation and not is_windows_admin():
        elev_err = (
            "خطأ أمني: يتطلب إجراء الاسترداد الطارئ لحساب المدير تشغيل العملية بصلاحيات مسؤول نظام التشغيل Windows (Run as Administrator).\n"
            "Security Error: Elevated Windows Administrator privileges are required to perform emergency recovery."
        )
        print("\n" + "=" * 70, flush=True)
        print(" [!] أكاديمية الشرطة — كلية الدراسات العليا", flush=True)
        print(" [!] " + elev_err, flush=True)
        print("=" * 70 + "\n", flush=True)
        if '--no-popup' not in sys.argv and not os.environ.get('CI'):
            try:
                ctypes.windll.user32.MessageBoxW(0, elev_err, "خطأ أمني — صلاحيات غير كافية", 0x10)
            except Exception:
                pass
        sys.exit(5)

    # 2. قراءة وسائط سطر الأوامر
    target_user = None
    new_password = None
    recovery_pin = None
    confirmed = any(arg in sys.argv for arg in ['--confirm', '--confirm-emergency-reset', '--yes'])

    for arg in sys.argv:
        if arg.startswith('--password='):
            new_password = arg.split('=', 1)[1]
        elif arg.startswith('--user='):
            target_user = arg.split('=', 1)[1]
        elif arg.startswith('--pin='):
            recovery_pin = arg.split('=', 1)[1]

    fallback_root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ArabicAcademicPlagiarismSystem' / 'Data'
    data_root = Path(os.environ.get('ARABIC_APP_DATA_DIR', fallback_root))
    data_db = data_root / 'Database' / 'papers.db'
    roaming_db = Path.home() / 'AppData' / 'Roaming' / 'ArabicPlagiarismDetector' / 'papers.db'
    local_db = Path(root_path) / 'papers.db'

    candidate_dbs = [db for db in [data_db, roaming_db, local_db] if db.exists()]
    if not candidate_dbs:
        print("[!] لم يتم العثور على قاعدة بيانات مهيأة للاسترداد.", flush=True)
        sys.exit(1)

    success = False
    last_res = None
    for db_path in candidate_dbs:
        ok, res_data, msg, err_code = perform_emergency_admin_reset(
            db_path=db_path,
            new_password=new_password,
            target_user=target_user,
            confirmed=confirmed,
            interactive=True,
            recovery_pin=recovery_pin,
            bypass_elevation_for_test=bypass_elevation
        )
        if ok:
            success = True
            last_res = res_data
        else:
            print(f"[!] خطأ في {db_path.name}: {msg}", flush=True)
            if err_code in ["ACCESS_DENIED", "CONFIRMATION_REQUIRED", "PASSWORD_TOO_WEAK", "CANCELLED", "PASSWORD_REQUIRED"]:
                sys.exit(1)

    if success and last_res:
        summary = (
            "تم استرداد وتعيين بيانات مدير المنظومة بنجاح تام!\n\n"
            f"اسم المستخدم (Username) : {last_res['username']}\n"
            f"الاسم الكامل            : {last_res['full_name']}\n"
            "حالة كلمة المرور        : تم التحديث وإبطال صلاحية الجلسات السابقة فوراً\n"
            "----------------------------------------------------------------------\n"
            "[مفتاح استرداد الحساب دون إنترنت البديل الجديد]:\n"
            f"رمز الاسترداد المكتبي   : {last_res['manual_recovery_code']}\n"
            f"رمز PIN لبطاقة الاسترداد: {last_res['recovery_pin']}\n"
            "----------------------------------------------------------------------\n"
            "* يرجى تدوين هذا الرمز وحفظه في خزنة المؤسسة لاستخدامه في الطوارئ.\n"
            f"* مسؤول نظام التشغيل المنفّذ: {last_res['os_user']}"
        )

        print("\n" + "=" * 70, flush=True)
        print("      أكاديمية الشرطة — منظومة كشف الاستلال العلمي", flush=True)
        print("             الاسترداد الطارئ لحساب مدير المنظومة", flush=True)
        print("=" * 70, flush=True)
        print(summary, flush=True)
        print("=" * 70 + "\n", flush=True)

        if '--no-popup' not in sys.argv and not os.environ.get('CI'):
            try:
                ctypes.windll.user32.MessageBoxW(0, summary, "استرداد حساب مدير المنظومة", 0x40)
            except Exception:
                pass

        sys.exit(0)
    else:
        print("[!] تعذر إتمام الاسترداد الطارئ لحساب المدير.", flush=True)
        sys.exit(1)
    sys.path.insert(0, bundle_path)

import config
from app.single_exe.app_controller import AppController, is_port_in_use, configured_worker_count


def main():
    # معالجة الوسائط السريعة
    is_headless = '--headless' in sys.argv or '--cli' in sys.argv
    port = int(os.environ.get('PORT', 5000))
    for arg in sys.argv[1:]:
        if arg.startswith('--port='):
            try:
                port = int(arg.split('=', 1)[1])
            except ValueError:
                pass
    host = os.environ.get('HOST', '0.0.0.0')

    controller = AppController(host=host, port=port, num_workers=configured_worker_count())

    # 1. فحص النسخة المكررة (Single Instance Check)
    if controller.check_single_instance():
        if not is_headless:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
        else:
            print(f"[!] System is already running at http://127.0.0.1:{port}", flush=True)
        sys.exit(0)

    # 2. بدء تشغيل المنظومة بصمت (Waitress + Workers + DB Init)
    try:
        controller.start(auto_open_browser=(not is_headless))
    except Exception as e:
        import traceback
        import uuid
        ref_id = f"ERR-STARTUP-2026-{uuid.uuid4().hex[:8].upper()}"
        tb = traceback.format_exc()
        
        # تصنيف الخطأ لرسالة واضحة للمستخدم
        err_str = str(e)
        if "Address already in use" in err_str or "PORT_IN_USE" in err_str or "10048" in err_str:
            user_facing_msg = f"المنفذ {port} مشغول حالياً بواسطة تطبيق آخر.\nيرجى إغلاق التطبيق الذي يستخدم هذا المنفذ أو إعادة المحاولة."
        elif "Cannot write to application data directory" in err_str or "PermissionError" in err_str:
            user_facing_msg = "تعذر الكتابة في مجلد بيانات التطبيق المحلي.\nيرجى التحقق من أذونات مجلد البيانات الخاص بالمستخدم."
        elif "Insufficient disk space" in err_str:
            user_facing_msg = f"المساحة الحرة على القرص الصلب غير كافية لتشغيل المنظومة.\n{err_str}"
        elif "PRODUCTION WSGI SERVER NOT AVAILABLE" in err_str:
            user_facing_msg = "خادم الإنتاج المعتمد (Waitress WSGI) غير متاح.\nتم إيقاف التشغيل وفقاً لسياسة الأمان الصارمة."
        else:
            user_facing_msg = f"حدث خطأ غير متوقع أثناء تهيئة المنظومة:\n{err_str}"

        crash_log_path = str(controller.logs_dir / 'startup_crash.log')
        try:
            with open(crash_log_path, 'w', encoding='utf-8') as f:
                f.write(f"Reference ID: {ref_id}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Error Message: {err_str}\n\n")
                f.write(f"Traceback:\n{tb}\n")
        except Exception:
            pass

        if not is_headless:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                dialog_text = (
                    f"⚠️ فشل بدء تشغيل المنظومة\n\n"
                    f"{user_facing_msg}\n\n"
                    f"معرّف المرجع (Reference ID): {ref_id}\n"
                    f"مسار السجلات: {crash_log_path}"
                )
                messagebox.showerror("خطأ حرج في الإقلاع — منظومة فحص الاستلال", dialog_text)
                root.destroy()
            except Exception:
                pass

        print(f"[CRITICAL] {ref_id}: {err_str}\n{tb}", file=sys.stderr)
        sys.exit(1)

    # 3. تشغيل أيقونة شريط المهام ولوحة الإدارة المخفية
    if not is_headless:
        try:
            from app.single_exe.gui_controller import ControlCenterGUI
            from app.single_exe.tray_controller import TrayController

            gui = ControlCenterGUI(controller, start_hidden='--show-console' not in sys.argv)
            tray = TrayController(controller, gui)
            tray.start()
            gui.run()  # blocks until Tkinter mainloop exits
            # If mainloop exited because the user chose shutdown via GUI → exit cleanly.
            if not controller.is_running:
                return
            # Otherwise (tray/GUI glitch) fall through to headless keep-alive below.
        except Exception as e:
            print(f"GUI/tray unavailable (falling back to headless keep-alive): {e}")


    # وضع التشغيل الخلفي / الطرفي إذا تعذرت الواجهة الرسومية
    print(f"[OK] Arabic Academic Plagiarism Detector is running on http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")

    def handle_exit(sig, frame):
        print("\nStopping system...")
        try:
            controller.stop()
        except Exception as exc:
            print(f"Shutdown incomplete: {controller.shutdown_detail or exc}")
            print('Outstanding work remains alive. Retry Ctrl+C after it finishes.')
            return
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass

    try:
        while controller.is_running or controller.shutdown_status in ('draining', 'incomplete'):
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit(None, None)


if __name__ == '__main__':
    main()
