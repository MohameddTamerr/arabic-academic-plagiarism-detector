# -*- coding: utf-8 -*-
"""
وحدة التحكم بأيقونة شريط المهام لنظام ويندوز (Native Win32 System Tray Controller):
- تنشئ أيقونة صغيرة بجانب ساعة ويندوز (System Notification Tray Area).
- تدعم قائمة سياقية (Context Menu) بالعربية والإنجليزية للإجراءات الإدارية.
- تتيح فتح المنظومة في المتصفح، استعراض السجلات، النسخ الاحتياطي، وإظهار لوحة الإدارة عند الطلب.
- تعمل في خيط خلفي مستقل مع تصريف رسائل Win32 القياسية دون التأثير على خادم الويب.
"""

import os
import sys
import threading
import webbrowser
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# استيراد واجهات Win32 الأصلية
try:
    import win32gui
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class TrayController:
    """مشرف أيقونة شريط المهام في ويندوز مع قائمة الإجراءات السريعة."""

    WM_TRAY_CALLBACK = win32con.WM_USER + 20 if WIN32_AVAILABLE else 1044

    # معرفات عناصر القائمة (Menu IDs)
    ID_OPEN_SYSTEM = 1001
    ID_SYSTEM_STATUS = 1002
    ID_OPEN_LOGS = 1003
    ID_CREATE_BACKUP = 1004
    ID_CREATE_DIAGNOSTIC = 1005
    ID_ADMIN_CONSOLE = 1006
    ID_EXIT_SYSTEM = 1007

    def __init__(self, app_controller, gui_controller=None):
        self.controller = app_controller
        self.gui = gui_controller
        self.hwnd: Optional[int] = None
        self.thread: Optional[threading.Thread] = None
        self._running = False
        self._icon_loaded = False
        self._hicon = None

    def start(self):
        """بدء خيط أيقونة شريط المهام."""
        if not WIN32_AVAILABLE:
            logger.warning("Win32 GUI extensions not available; system tray disabled.")
            return

        self._running = True
        self.thread = threading.Thread(target=self._run_tray_loop, daemon=True, name="Win32TrayThread")
        self.thread.start()

    def stop(self):
        """إزالة أيقونة شريط المهام وإيقاف الخيط."""
        self._running = False
        if WIN32_AVAILABLE and self.hwnd:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
            except Exception:
                pass
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

    def _get_icon_handle(self):
        """استخراج مقبض الأيقونة HICON من ملفات التطبيق أو النظام."""
        if self._hicon:
            return self._hicon

        # البحث عن ملف favicon.ico
        icon_path = None
        try:
            import config
            bundle_dir = getattr(config, 'BUNDLE_DIR', config.BASE_DIR)
            candidate = bundle_dir / "static" / "favicon.ico"
            if candidate.exists():
                icon_path = str(candidate)
            else:
                candidate2 = Path("scratch/app.ico")
                if candidate2.exists():
                    icon_path = str(candidate2)
        except Exception:
            pass

        if icon_path and os.path.exists(icon_path):
            try:
                self._hicon = win32gui.LoadImage(
                    0,
                    icon_path,
                    win32con.IMAGE_ICON,
                    0,
                    0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
                )
                return self._hicon
            except Exception as e:
                logger.debug(f"Could not load custom icon from {icon_path}: {e}")

        # استخدام الأيقونة الافتراضية للتطبيق في نظام ويندوز
        try:
            self._hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            return self._hicon
        except Exception:
            return None

    def _run_tray_loop(self):
        """حلقة استقبال رسائل نافذة شريط المهام المخفية."""
        try:
            wc = win32gui.WNDCLASS()
            hinst = wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = f"ArabicPlagiarismTray_{os.getpid()}"
            wc.lpfnWndProc = self._wnd_proc

            class_atom = win32gui.RegisterClass(wc)
            self.hwnd = win32gui.CreateWindow(
                class_atom,
                "Arabic Plagiarism Detector Tray Window",
                win32con.WS_OVERLAPPED | win32con.WS_SYSMENU,
                0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
                0, 0, hinst, None
            )
            win32gui.UpdateWindow(self.hwnd)

            # إضافة الأيقونة إلى شريط المهام
            hicon = self._get_icon_handle()
            tip = "منظومة فحص الاستلال الأكاديمي (تعمل بنجاح)"
            flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
            nid = (self.hwnd, 0, flags, self.WM_TRAY_CALLBACK, hicon, tip)
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
            except Exception as tray_err:
                # System tray area may be unavailable (e.g. no Explorer shell).
                # This is non-fatal — Waitress keeps running without a tray icon.
                logger.warning(f"System tray icon unavailable (non-fatal): {tray_err}")
                return

            # ضخ الرسائل
            win32gui.PumpMessages()
        except Exception as e:
            logger.error(f"Error in System Tray message loop: {e}")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """معالج رسائل النافذة والتفاعل مع نقرات الأيقونة."""
        if msg == self.WM_TRAY_CALLBACK:
            if lparam == win32con.WM_RBUTTONUP:
                self._show_context_menu()
            elif lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
                self._on_open_system()
            return 0

        elif msg == win32con.WM_COMMAND:
            cmd_id = win32gui.LOWORD(wparam)
            self._handle_menu_command(cmd_id)
            return 0

        elif msg == win32con.WM_DESTROY:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
            except Exception:
                pass
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _show_context_menu(self):
        """عرض القائمة السياقية في موقع مؤشر الفأرة."""
        menu = win32gui.CreatePopupMenu()

        # بناء عناصر القائمة
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_OPEN_SYSTEM, "🌐  فتح المنظومة في المتصفح (Open System)")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_SYSTEM_STATUS, "📊  حالة النظام والجاهزية (System Status)")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_OPEN_LOGS, "📁  فتح مجلد السجلات (Open Logs)")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_CREATE_BACKUP, "💾  إنشاء نسخة احتياطية فورية (Create Backup)")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_CREATE_DIAGNOSTIC, "📦  تصدير حزمة التشخيص (Diagnostic Package)")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_ADMIN_CONSOLE, "⚙️  لوحة إدارة النظام (Admin Control Center)")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.ID_EXIT_SYSTEM, "🛑  إنهاء وإغلاق المنظومة (Exit System)")

        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
            pos[0],
            pos[1],
            0,
            self.hwnd,
            None
        )
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _handle_menu_command(self, cmd_id: int):
        """توجيه أمر القائمة المحدد."""
        if cmd_id == self.ID_OPEN_SYSTEM:
            self._on_open_system()
        elif cmd_id == self.ID_SYSTEM_STATUS:
            self._on_show_status()
        elif cmd_id == self.ID_OPEN_LOGS:
            self._on_open_logs()
        elif cmd_id == self.ID_CREATE_BACKUP:
            self._on_create_backup()
        elif cmd_id == self.ID_CREATE_DIAGNOSTIC:
            self._on_create_diagnostic()
        elif cmd_id == self.ID_ADMIN_CONSOLE:
            self._on_open_admin_console()
        elif cmd_id == self.ID_EXIT_SYSTEM:
            self._on_exit_system()

    def _on_open_system(self):
        """فتح واجهة النظام في المتصفح الافتراضي."""
        url = f"http://127.0.0.1:{self.controller.port}"
        webbrowser.open(url)

    def _on_show_status(self):
        """عرض بطاقة سريعة لحالة الجاهزية."""
        if self.gui:
            self.gui.dispatch_to_gui(self.gui.show_status_dialog)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                msg = (
                    f"🟢 منظومة فحص الاستلال الأكاديمي تعمل بنجاح\n\n"
                    f"الرابط المحلي: http://127.0.0.1:{self.controller.port}\n"
                    f"خادم الإنتاج: Waitress WSGI (3.0.2)\n"
                    f"عدد عمال الفحص: {self.controller.num_workers} عمال نشطين\n"
                    f"تخزين البيانات: محلي ومحمي بنمط WAL"
                )
                messagebox.showinfo("حالة المنظومة — System Status", msg)
                root.destroy()
            except Exception:
                pass

    def _on_open_logs(self):
        """فتح مجلد السجلات."""
        log_dir = self.controller.logs_dir
        if log_dir.exists():
            os.startfile(str(log_dir))

    def _on_create_backup(self):
        """طلب تأكيد وتنفيذ النسخ الاحتياطي."""
        if self.gui:
            self.gui.dispatch_to_gui(self.gui.create_backup_with_confirmation)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                confirm = messagebox.askyesno(
                    "تأكيد النسخ الاحتياطي",
                    "هل ترغب في إنشاء نسخة احتياطية فورية شاملة لقاعدة البيانات والوثائق؟"
                )
                if confirm:
                    res = self.controller.create_backup(label="tray")
                    messagebox.showinfo(
                        "اكتمل النسخ الاحتياطي",
                        f"تم إنشاء النسخة الاحتياطية بنجاح!\n\nالملف: {os.path.basename(res['backup_file'])}\nالحجم: {res['size_mb']} MB"
                    )
                root.destroy()
            except Exception as e:
                logger.error(f"Backup failed from tray: {e}")

    def _on_create_diagnostic(self):
        """طلب تأكيد وتصدير حزمة التشخيص."""
        if self.gui:
            self.gui.dispatch_to_gui(self.gui.create_diagnostic_with_confirmation)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                confirm = messagebox.askyesno(
                    "تأكيد تصدير حزمة التشخيص",
                    "هل ترغب في تجميع وتصدير حزمة تشخيصية للدعم الفني؟\n(الحزمة خالية تماماً من نصوص الأبحاث والبيانات السرية)"
                )
                if confirm:
                    zip_path = self.controller.create_diagnostic_package()
                    messagebox.showinfo(
                        "اكتملت حزمة التشخيص",
                        f"تم إنشاء حزمة التشخيص بنجاح!\n\nالملف: {os.path.basename(zip_path)}"
                    )
                root.destroy()
            except Exception as e:
                logger.error(f"Diagnostic failed from tray: {e}")

    def _on_open_admin_console(self):
        """إظهار نافذة لوحة إدارة النظام."""
        if self.gui:
            self.gui.dispatch_to_gui(self.gui.show_admin_console)

    def _on_exit_system(self):
        """طلب تأكيد الإغلاق وتنفيذ الإيقاف النظيف."""
        if self.gui:
            self.gui.dispatch_to_gui(self.gui.on_exit_request)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                confirm = messagebox.askyesno(
                    "تأكيد إيقاف المنظومة",
                    "هل أنت متأكد من رغبتك في إيقاف المنظومة بالكامل والخروج؟\n\nسيتم تجفيف مهام العمال وحفظ كافة المعاملات بأمان."
                )
                if confirm:
                    self.stop()
                    self.controller.stop()
                    root.destroy()
                    sys.exit(0)
                root.destroy()
            except Exception:
                pass
