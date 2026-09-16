# -*- coding: utf-8 -*-
"""
لوحة إدارة النظام المدمجة لمسؤولي النظام وتقنية المعلومات (Admin / IT Control Center):
- مخصصة للإدارة والتشخيص والصيانة وتعمل كأداة عند الطلب (On-Demand).
- تكون مخفية افتراضياً عند إقلاع المنظومة وتفتح فقط عبر أيقونة شريط المهام (Tray Menu).
- لا يسبب إغلاقها (X) إيقاف الخادم، بل يعيد إخفاءها إلى شريط المهام.
- الإجراءات الحساسة (النسخ الاحتياطي، تصدير التشخيص، الإيقاف) محمية بطلبات تأكيد صريحة.
"""

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional, Callable

from app.single_exe.app_controller import AppController


class ControlCenterGUI:
    """لوحة إدارة النظام والتشخيص المخصصة لمسؤولي النظام."""

    def __init__(self, controller: AppController, start_hidden: bool = True, root: Optional[tk.Tk] = None):
        self.controller = controller
        self.root = root if root is not None else tk.Tk()
        self.root.title("لوحة إدارة النظام — System Administration Console")
        self.root.geometry("640x590")
        self.root.resizable(False, False)

        # محاولة تعيين الأيقونة الرسمية
        try:
            from pathlib import Path
            import config
            bundle_dir = getattr(config, 'BUNDLE_DIR', config.BASE_DIR)
            icon_path = bundle_dir / "static" / "favicon.ico"
            if not icon_path.exists():
                icon_path = Path("scratch/app.ico")
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

        self._build_ui()

        # إغلاق النافذة عبر (X) يخفيها إلى شريط المهام ولا يوقف المنظومة
        self.root.protocol("WM_DELETE_WINDOW", self.hide_admin_console)

        # الإخفاء الافتراضي عند بدء التشغيل
        if start_hidden:
            self.root.withdraw()

    def _build_ui(self):
        """بناء عناصر واجهة لوحة الإدارة."""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        main_frame = ttk.Frame(self.root, padding="16 16 16 16")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # الترويسة الإدارية
        header_frame = tk.Frame(main_frame, bg="#0f172a", padx=12, pady=12)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        title_lbl = tk.Label(
            header_frame,
            text="⚙️ لوحة إدارة النظام والتشخيص",
            font=("Segoe UI", 15, "bold"),
            fg="white",
            bg="#0f172a"
        )
        title_lbl.pack()

        subtitle_lbl = tk.Label(
            header_frame,
            text="System Administration & Diagnostics Console (IT / Admin)",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a"
        )
        subtitle_lbl.pack(pady=(2, 0))

        # بطاقة الجاهزية والخادم
        status_card = ttk.LabelFrame(main_frame, text=" حالة الخادم والجاهزية ", padding="10 8 10 8")
        status_card.pack(fill=tk.X, pady=(0, 10))

        # صف الحالة
        status_row = ttk.Frame(status_card)
        status_row.pack(fill=tk.X, pady=2)
        ttk.Label(status_row, text="حالة الخادم:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.lbl_status = ttk.Label(status_row, text="🟢 خادم الإنتاج يعمل وجاهز لاستقبال الطلبات (Online)", font=("Segoe UI", 9), foreground="#059669")
        self.lbl_status.pack(side=tk.LEFT, padx=(8, 0))

        # صف الخادم والمنفذ
        ws_row = ttk.Frame(status_card)
        ws_row.pack(fill=tk.X, pady=2)
        ttk.Label(ws_row, text="خادم WSGI:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(ws_row, text="Waitress 3.0.2 (مفعل وإلزامي)", font=("Segoe UI", 9), foreground="#0f766e").pack(side=tk.LEFT, padx=(8, 15))
        ttk.Label(ws_row, text="المنفذ المحلي:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(ws_row, text=f"http://127.0.0.1:{self.controller.port}", font=("Segoe UI", 9, "underline"), foreground="#2563eb", cursor="hand2").pack(side=tk.LEFT, padx=(8, 0))

        # صف عمال الفحص
        comp_row = ttk.Frame(status_card)
        comp_row.pack(fill=tk.X, pady=2)
        ttk.Label(comp_row, text="عمال المعالجة الخلفية:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(comp_row, text=f"{self.controller.num_workers} عمال نشطين", font=("Segoe UI", 9), foreground="#059669").pack(side=tk.LEFT, padx=(8, 15))
        ttk.Label(comp_row, text="عنوان الشبكة:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(comp_row, text=f"http://{self.controller.lan_ip}:{self.controller.port}", font=("Segoe UI", 9), foreground="#475569").pack(side=tk.LEFT, padx=(8, 0))

        # بطاقة مسارات البيانات
        paths_card = ttk.LabelFrame(main_frame, text=" التخزين المحلي والبيانات ", padding="10 6 10 6")
        paths_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(paths_card, text="📁 تخزين البيانات المحلي: نشط ومحمي (Local Data Storage: Active)", font=("Segoe UI", 9, "bold"), foreground="#0f766e").pack(anchor=tk.W)
        ttk.Label(paths_card, text="قاعدة البيانات: SQLite معزولة ومستدامة محلياً بنمط WAL الآمن", font=("Segoe UI", 8), foreground="#475569").pack(anchor=tk.W, pady=(1, 0))

        # قسم الإجراءات الإدارية
        actions_frame = ttk.LabelFrame(main_frame, text=" العمليات الإدارية والصيانة ", padding="10 10 10 10")
        actions_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # أزرار الإجراءات
        btn_browser = tk.Button(
            actions_frame,
            text="🌐 فتح المنظومة في المتصفح",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief=tk.FLAT,
            padx=8,
            pady=6,
            command=self.open_browser
        )
        btn_browser.grid(row=0, column=0, sticky="nsew", padx=5, pady=4)

        btn_logs = tk.Button(
            actions_frame,
            text="📁 فتح مجلد السجلات",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#0f172a",
            relief=tk.GROOVE,
            padx=8,
            pady=6,
            command=self.open_logs
        )
        btn_logs.grid(row=0, column=1, sticky="nsew", padx=5, pady=4)

        btn_backup = tk.Button(
            actions_frame,
            text="💾 إنشاء نسخة احتياطية فورية",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#0f172a",
            relief=tk.GROOVE,
            padx=8,
            pady=6,
            command=self.create_backup_with_confirmation
        )
        btn_backup.grid(row=1, column=0, sticky="nsew", padx=5, pady=4)

        btn_diag = tk.Button(
            actions_frame,
            text="📦 تصدير حزمة التشخيص",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#0f172a",
            relief=tk.GROOVE,
            padx=8,
            pady=6,
            command=self.create_diagnostic_with_confirmation
        )
        btn_diag.grid(row=1, column=1, sticky="nsew", padx=5, pady=4)

        btn_errors = tk.Button(
            actions_frame,
            text="⚠️ عرض الأخطاء الحديثة",
            font=("Segoe UI", 9),
            bg="#fef2f2",
            fg="#991b1b",
            relief=tk.GROOVE,
            padx=8,
            pady=6,
            command=self.view_recent_errors
        )
        btn_errors.grid(row=2, column=0, sticky="nsew", padx=5, pady=4)

        btn_hide = tk.Button(
            actions_frame,
            text="🔒 إخفاء اللوحة إلى شريط المهام",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg="#334155",
            relief=tk.GROOVE,
            padx=8,
            pady=6,
            command=self.hide_admin_console
        )
        btn_hide.grid(row=2, column=1, sticky="nsew", padx=5, pady=4)

        # زر إيقاف المنظومة الكامل
        btn_exit = tk.Button(
            main_frame,
            text="🛑 إيقاف وإغلاق المنظومة بالكامل (Exit System)",
            font=("Segoe UI", 9, "bold"),
            bg="#dc2626",
            fg="white",
            activebackground="#b91c1c",
            activeforeground="white",
            relief=tk.FLAT,
            padx=10,
            pady=6,
            command=self.on_exit_request
        )
        btn_exit.pack(fill=tk.X, pady=(0, 2))

        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)

    def dispatch_to_gui(self, func: Callable, *args, **kwargs):
        """توجيه استدعاء من خيط آخر إلى خيط الواجهة الرسومية الرئيسي بأمان."""
        try:
            self.root.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def show_admin_console(self):
        """إظهار لوحة إدارة النظام وجلبها للمقدمة."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_admin_console(self):
        """إخفاء لوحة إدارة النظام إلى شريط المهام دون إيقاف الخادم."""
        self.root.withdraw()

    def show_status_dialog(self):
        """عرض بطاقة سريعة لحالة الجاهزية من شريط المهام."""
        msg = (
            f"🟢 منظومة فحص الاستلال الأكاديمي تعمل بنجاح\n\n"
            f"الرابط المحلي: http://127.0.0.1:{self.controller.port}\n"
            f"خادم الإنتاج: Waitress WSGI (3.0.2)\n"
            f"عدد عمال الفحص: {self.controller.num_workers} عمال نشطين\n"
            f"تخزين البيانات: محلي ومحمي بنمط WAL"
        )
        messagebox.showinfo("حالة المنظومة — System Status", msg, parent=self.root)

    def open_browser(self):
        """فتح التطبيق في المتصفح الافتراضي."""
        url = f"http://127.0.0.1:{self.controller.port}"
        webbrowser.open(url)

    def open_logs(self):
        """فتح مجلد السجلات في مستكشف ويندوز."""
        log_dir = self.controller.logs_dir
        if log_dir.exists():
            os.startfile(str(log_dir))
        else:
            messagebox.showinfo("تنبيه", "مجلد السجلات لم يتم إنشاؤه بعد.", parent=self.root)

    def view_recent_errors(self):
        """عرض أحدث الأخطاء المسجلة."""
        errors_text = self.controller.get_recent_errors(max_lines=100)
        
        top = tk.Toplevel(self.root)
        top.title("سجل الأخطاء الحديثة (Recent Errors)")
        top.geometry("620x400")
        top.transient(self.root)
        
        lbl = ttk.Label(top, text="آخر السجلات من ملف errors.log:", font=("Segoe UI", 9, "bold"))
        lbl.pack(anchor=tk.W, padx=10, pady=(10, 4))
        
        txt = scrolledtext.ScrolledText(top, wrap=tk.WORD, font=("Consolas", 9), bg="#1e293b", fg="#f8fafc")
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        txt.insert(tk.END, errors_text)
        txt.config(state=tk.DISABLED)

    def create_backup_with_confirmation(self):
        """طلب تأكيد صريح ثم إنشاء نسخة احتياطية حية."""
        confirm = messagebox.askyesno(
            "تأكيد النسخ الاحتياطي",
            "هل ترغب في إنشاء نسخة احتياطية فورية شاملة لقاعدة البيانات والوثائق؟",
            parent=self.root
        )
        if not confirm:
            return

        try:
            res = self.controller.create_backup(label="admin_console")
            msg = (
                f"تم إنشاء النسخة الاحتياطية بنجاح!\n\n"
                f"الملف: {os.path.basename(res['backup_file'])}\n"
                f"الحجم: {res['size_mb']} MB\n"
                f"عدد الأبحاث: {res['research_count']}\n"
                f"بصمة النزاهة (Integrity Checksum):\n{res['sha256_checksum']}\n\n"
                f"المسار: {res['backup_file']}"
            )
            messagebox.showinfo("اكتمل النسخ الاحتياطي", msg, parent=self.root)
        except Exception as e:
            messagebox.showerror("خطأ في النسخ الاحتياطي", f"تعذر إنشاء النسخة الاحتياطية: {e}", parent=self.root)

    def create_diagnostic_with_confirmation(self):
        """طلب تأكيد صريح ثم إنشاء حزمة تشخيصية آمنة."""
        confirm = messagebox.askyesno(
            "تأكيد تصدير حزمة التشخيص",
            "هل ترغب في تجميع وتصدير حزمة تشخيصية للدعم الفني؟\n\n"
            "ملاحظة: الحزمة خالية تماماً من نصوص الأبحاث والبيانات السرية.",
            parent=self.root
        )
        if not confirm:
            return

        try:
            zip_path = self.controller.create_diagnostic_package()
            msg = (
                f"تم إنشاء الحزمة التشخيصية بنجاح!\n\n"
                f"الملف: {os.path.basename(zip_path)}\n\n"
                f"هذه الحزمة خالية تماماً من نصوص الأبحاث وقواعد البيانات والكلمات السرية، "
                f"وتصلح للمشاركة مع الدعم الفني.\n\n"
                f"المسار: {zip_path}"
            )
            messagebox.showinfo("اكتمل إنشاء الحزمة التشخيصية", msg, parent=self.root)
        except Exception as e:
            messagebox.showerror("خطأ في التشخيص", f"تعذر إنشاء الحزمة التشخيصية: {e}", parent=self.root)

    def on_exit_request(self):
        """طلب تأكيد الإغلاق وتنفيذ الإيقاف النظيف للخدمة والعمال."""
        confirm = messagebox.askyesno(
            "تأكيد إيقاف المنظومة",
            "هل أنت متأكد من رغبتك في إيقاف المنظومة بالكامل والخروج؟\n\n"
            "سيتم تجفيف مهام العمال وحفظ كافة معاملات قاعدة البيانات بأمان.",
            parent=self.root
        )
        if confirm:
            self.lbl_status.config(text="🟡 جاري حفظ البيانات والإيقاف بأمان...", foreground="#d97706")
            self.root.update()
            self.controller.stop()
            self.root.destroy()
            sys.exit(0)

    def run(self):
        """بدء حلقة الواجهة الرسومية المخفية."""
        self.root.mainloop()
