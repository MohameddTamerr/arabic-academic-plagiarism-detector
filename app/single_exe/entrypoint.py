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


# إضافة مسار المشروع ومجلد vendor إن وجدا
root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

vendor_path = os.path.join(root_path, 'vendor')
if os.path.exists(vendor_path) and vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

bundle_path = getattr(sys, '_MEIPASS', None)
if bundle_path and bundle_path not in sys.path:
    sys.path.insert(0, bundle_path)

import config
from app.single_exe.app_controller import AppController, is_port_in_use


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

    controller = AppController(host=host, port=port, num_workers=2)

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

            gui = ControlCenterGUI(controller, start_hidden=True)
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
        controller.stop()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass

    try:
        while controller.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit(None, None)


if __name__ == '__main__':
    main()
