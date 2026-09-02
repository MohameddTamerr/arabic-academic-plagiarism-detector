# -*- coding: utf-8 -*-
"""
واجهة المستخدم الرئيسية باستخدام tkinter.
تدعم:
- إدارة قاعدة الأبحاث (إضافة مجلد كامل أو ملف واحد)
- فحص بحث جديد (PDF / DOCX / نص مكتوب مباشرة)
- عرض التقرير مع تلوين النص (أحمر=نسخ، برتقالي=إعادة صياغة)
- عرض جدول المصادر المكتشفة
- حفظ التقرير كملف HTML
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import logging

# ── إعداد مسار المشروع والـ vendor عند التشغيل من أي مكان ──────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.dirname(os.path.dirname(_HERE))  # مجلد Baba
_VENDOR = os.path.join(_ROOT, 'vendor')
for _p in [_ROOT, _VENDOR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from plagiarism_detector.core import db, detector
from plagiarism_detector.core.extractor import extract_text
from plagiarism_detector.core.normalize import normalize_arabic

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


# ─────────────────────────────────────────────────────────────────────────────
# ألوان ومتغيرات التصميم
# ─────────────────────────────────────────────────────────────────────────────
BG_DARK    = '#1e1e2e'
BG_PANEL   = '#2a2a3e'
BG_CARD    = '#313147'
ACCENT     = '#7c6af7'
ACCENT2    = '#a78bfa'
RED_COPY   = '#ff6b6b'
ORANGE_PAR = '#ffa94d'
GREEN_OK   = '#69db7c'
TEXT_MAIN  = '#e2e0ff'
TEXT_SUB   = '#9999bb'
FONT_AR    = ('Segoe UI', 11)
FONT_AR_B  = ('Segoe UI', 11, 'bold')
FONT_TITLE = ('Segoe UI', 18, 'bold')
FONT_MONO  = ('Consolas', 10)


class PlagiarismApp(tk.Tk):
    """النافذة الرئيسية للتطبيق."""

    def __init__(self):
        super().__init__()
        self.title('كاشف الانتحال الأكاديمي العربي')
        self.geometry('1180x760')
        self.minsize(900, 600)
        self.configure(bg=BG_DARK)

        # تفعيل RTL على مستوى النافذة
        try:
            self.tk.call('tk', 'appname', 'ArabicPlagiarism')
        except Exception:
            pass

        db.init_db()
        self._build_ui()
        self._refresh_paper_count()

    # ──────────────────────────────────────────────────────────────────────────
    # بناء الواجهة
    # ──────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ─── شريط علوي ───────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG_PANEL, height=60)
        header.pack(fill='x', side='top')
        tk.Label(header, text='كاشف الانتحال الأكاديمي العربي',
                 bg=BG_PANEL, fg=ACCENT2, font=FONT_TITLE,
                 pady=12, padx=20).pack(side='right')

        self._count_lbl = tk.Label(header, text='', bg=BG_PANEL,
                                   fg=TEXT_SUB, font=FONT_AR)
        self._count_lbl.pack(side='left', padx=20)

        # ─── Notebook (تبويبات) ───────────────────────────────────────────────
        style = ttk.Style(self)
        style.theme_use('default')
        style.configure('TNotebook', background=BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=BG_PANEL, foreground=TEXT_SUB,
                        padding=[16, 8], font=FONT_AR)
        style.map('TNotebook.Tab',
                  background=[('selected', BG_CARD)],
                  foreground=[('selected', ACCENT2)])
        style.configure('TFrame', background=BG_DARK)

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=10)

        # التبويب الأول: إدارة قاعدة الأبحاث
        tab_db = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_db, text='  قاعدة الأبحاث المرجعية  ')
        self._build_db_tab(tab_db)

        # التبويب الثاني: فحص بحث جديد
        tab_check = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_check, text='  فحص بحث جديد  ')
        self._build_check_tab(tab_check)

        # التبويب الثالث: نتائج آخر فحص
        tab_result = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_result, text='  نتيجة الفحص والتحليل  ')
        self._build_result_tab(tab_result)

        self._nb = nb

    # ─── تبويب إدارة قاعدة الأبحاث ──────────────────────────────────────────
    def _build_db_tab(self, parent):
        # أزرار الإضافة
        btn_frame = tk.Frame(parent, bg=BG_DARK)
        btn_frame.pack(fill='x', padx=16, pady=12)

        self._make_btn(btn_frame, 'إضافة ملف بحث', self._add_single_file).pack(side='right', padx=6)
        self._make_btn(btn_frame, 'إضافة مجلد أبحاث', self._add_folder).pack(side='right', padx=6)
        self._make_btn(btn_frame, 'إعادة بناء الفهرس', self._rebuild_index,
                       color=ACCENT).pack(side='right', padx=6)
        self._make_btn(btn_frame, 'حذف المحدد', self._delete_selected,
                       color='#e74c3c').pack(side='left', padx=6)

        # جدول الأبحاث
        cols = ('id', 'title', 'file_path', 'added_at')
        headers = ('#', 'عنوان البحث', 'مسار الملف', 'تاريخ الإضافة')
        col_widths = (40, 350, 280, 140)

        style = ttk.Style()
        style.configure('Papers.Treeview', background=BG_CARD, foreground=TEXT_MAIN,
                        fieldbackground=BG_CARD, rowheight=28, font=FONT_AR)
        style.configure('Papers.Treeview.Heading', background=BG_PANEL,
                        foreground=ACCENT2, font=FONT_AR_B)
        style.map('Papers.Treeview', background=[('selected', ACCENT)])

        tree_frame = tk.Frame(parent, bg=BG_DARK)
        tree_frame.pack(fill='both', expand=True, padx=16, pady=(0, 12))

        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical')
        self._tree = ttk.Treeview(tree_frame, columns=cols, show='headings',
                                  style='Papers.Treeview',
                                  yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._tree.yview)

        for col, header, width in zip(cols, headers, col_widths):
            self._tree.heading(col, text=header, anchor='e')
            self._tree.column(col, width=width, anchor='e')

        scrollbar.pack(side='left', fill='y')
        self._tree.pack(side='right', fill='both', expand=True)

        # شريط التقدم للإضافة
        self._db_progress = ttk.Progressbar(parent, mode='indeterminate')
        self._db_progress.pack(fill='x', padx=16, pady=(0, 4))

        self._db_status = tk.Label(parent, text='', bg=BG_DARK, fg=TEXT_SUB, font=FONT_AR)
        self._db_status.pack()

        self._refresh_table()

    # ─── تبويب فحص البحث ─────────────────────────────────────────────────────
    def _build_check_tab(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill='x', padx=16, pady=12)

        self._make_btn(top, 'استعراض ملف للفحص (PDF/DOCX/TXT)',
                       self._load_check_file).pack(side='right', padx=6)
        self._make_btn(top, 'بدء الفحص والتحليل', self._start_check,
                       color=GREEN_OK).pack(side='right', padx=6)

        # منطقة الإدخال (نص مكتوب يدويًا أو محمّل من ملف)
        input_label = tk.Label(parent, text='أو الصق نص البحث هنا مباشرة:',
                               bg=BG_DARK, fg=TEXT_SUB, font=FONT_AR, anchor='e')
        input_label.pack(fill='x', padx=16)

        self._input_text = scrolledtext.ScrolledText(
            parent, height=18, wrap='word',
            bg=BG_CARD, fg=TEXT_MAIN, font=FONT_AR,
            insertbackground=ACCENT2,
            relief='flat', padx=12, pady=8
        )
        self._input_text.pack(fill='both', expand=True, padx=16, pady=(4, 8))

        # شريط التقدم
        self._check_progress = ttk.Progressbar(parent, mode='indeterminate')
        self._check_progress.pack(fill='x', padx=16, pady=(0, 4))
        self._check_status = tk.Label(parent, text='جاهز للفحص',
                                      bg=BG_DARK, fg=TEXT_SUB, font=FONT_AR)
        self._check_status.pack()

    # ─── تبويب النتائج ────────────────────────────────────────────────────────
    def _build_result_tab(self, parent):
        # بطاقات الإحصاء
        self._stats_frame = tk.Frame(parent, bg=BG_DARK)
        self._stats_frame.pack(fill='x', padx=16, pady=12)

        self._stat_overall  = self._make_stat_card(self._stats_frame, 'نسبة الاقتباس الكلية', '—', ACCENT)
        self._stat_copied   = self._make_stat_card(self._stats_frame, 'نسخ حرفي', '—', RED_COPY)
        self._stat_para     = self._make_stat_card(self._stats_frame, 'إعادة صياغة', '—', ORANGE_PAR)
        self._stat_original = self._make_stat_card(self._stats_frame, 'نص أصلي', '—', GREEN_OK)

        # زر حفظ التقرير
        btn_row = tk.Frame(parent, bg=BG_DARK)
        btn_row.pack(fill='x', padx=16, pady=(0, 8))
        self._make_btn(btn_row, 'تصدير التقرير (HTML)', self._save_report).pack(side='left', padx=6)

        # النص الملوّن
        result_label = tk.Label(parent, text='النص المحلَّل (اللون يشير إلى نوع الاقتباس):',
                                bg=BG_DARK, fg=TEXT_SUB, font=FONT_AR, anchor='e')
        result_label.pack(fill='x', padx=16)

        self._result_text = scrolledtext.ScrolledText(
            parent, height=14, wrap='word',
            bg=BG_CARD, fg=TEXT_MAIN, font=FONT_AR,
            relief='flat', padx=12, pady=8, state='disabled'
        )
        self._result_text.pack(fill='both', expand=True, padx=16, pady=(4, 4))

        # جدول المصادر
        src_label = tk.Label(parent, text='المصادر المكتشفة:',
                             bg=BG_DARK, fg=TEXT_SUB, font=FONT_AR, anchor='e')
        src_label.pack(fill='x', padx=16)

        src_frame = tk.Frame(parent, bg=BG_DARK)
        src_frame.pack(fill='x', padx=16, pady=(2, 12))

        style = ttk.Style()
        style.configure('Src.Treeview', background=BG_CARD, foreground=TEXT_MAIN,
                        fieldbackground=BG_CARD, rowheight=24, font=FONT_AR)
        style.configure('Src.Treeview.Heading', background=BG_PANEL,
                        foreground=ACCENT2, font=FONT_AR_B)

        self._src_tree = ttk.Treeview(src_frame, columns=('rank', 'title', 'pct'),
                                       show='headings', height=5, style='Src.Treeview')
        for col, hdr, w in [('rank', '#', 40), ('title', 'عنوان المصدر', 480), ('pct', 'نسبة التطابق', 120)]:
            self._src_tree.heading(col, text=hdr, anchor='e')
            self._src_tree.column(col, width=w, anchor='e')
        self._src_tree.pack(fill='x')

        # حفظ التقرير الأخير
        self._last_report = None

    # ──────────────────────────────────────────────────────────────────────────
    # مساعدات بناء الواجهة
    # ──────────────────────────────────────────────────────────────────────────
    def _make_btn(self, parent, text, cmd, color=None):
        bg = color or ACCENT
        btn = tk.Button(parent, text=text, command=cmd,
                        bg=bg, fg='white', activebackground=ACCENT2,
                        activeforeground='white', relief='flat',
                        font=FONT_AR, padx=14, pady=7, cursor='hand2',
                        bd=0)
        return btn

    def _make_stat_card(self, parent, label, value, color):
        card = tk.Frame(parent, bg=BG_CARD, padx=20, pady=14)
        card.pack(side='right', padx=8, fill='y')
        tk.Label(card, text=label, bg=BG_CARD, fg=TEXT_SUB, font=FONT_AR).pack()
        val_lbl = tk.Label(card, text=value, bg=BG_CARD, fg=color,
                           font=('Segoe UI', 22, 'bold'))
        val_lbl.pack()
        return val_lbl

    # ──────────────────────────────────────────────────────────────────────────
    # إدارة قاعدة البيانات
    # ──────────────────────────────────────────────────────────────────────────
    def _add_single_file(self):
        path = filedialog.askopenfilename(
            title='اختر ملف بحث',
            filetypes=[('ملفات مدعومة', '*.pdf *.docx *.doc *.txt'),
                       ('PDF', '*.pdf'), ('Word', '*.docx *.doc'), ('نص', '*.txt')]
        )
        if path:
            self._import_files([path])

    def _add_folder(self):
        folder = filedialog.askdirectory(title='اختر مجلد الأبحاث')
        if not folder:
            return
        files = []
        for root, _, filenames in os.walk(folder):
            for fn in filenames:
                if fn.lower().endswith(('.pdf', '.docx', '.doc', '.txt')):
                    files.append(os.path.join(root, fn))
        if not files:
            messagebox.showwarning('تنبيه', 'لا توجد ملفات مدعومة في المجلد المختار.')
            return
        self._import_files(files)

    def _import_files(self, file_list: list[str]):
        """يستورد الملفات في thread خلفي عشان ما يجمّد الواجهة."""
        self._db_progress.start()
        self._db_status.config(text='جاري الاستيراد...')

        def worker():
            added = 0
            skipped = 0
            for path in file_list:
                title = os.path.splitext(os.path.basename(path))[0]
                if db.paper_exists(title):
                    skipped += 1
                    continue
                text = extract_text(path)
                if text.strip():
                    db.add_paper(title, text, path)
                    db.invalidate_index()
                    added += 1
                else:
                    skipped += 1

            self.after(0, lambda: self._import_done(added, skipped))

        threading.Thread(target=worker, daemon=True).start()

    def _import_done(self, added, skipped):
        self._db_progress.stop()
        self._db_status.config(text=f'تمت الإضافة: {added} بحث  |  تم تجاهله: {skipped}')
        self._refresh_table()
        self._refresh_paper_count()

    def _rebuild_index(self):
        self._db_progress.start()
        self._db_status.config(text='جاري إعادة بناء الفهرس...')

        def worker():
            db.invalidate_index()
            detector.build_index()
            self.after(0, self._rebuild_done)

        threading.Thread(target=worker, daemon=True).start()

    def _rebuild_done(self):
        self._db_progress.stop()
        self._db_status.config(text='تم إعادة بناء الفهرس بنجاح')

    def _delete_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        if not messagebox.askyesno('تأكيد', f'هل تريد حذف {len(selected)} بحث/بحوث؟'):
            return
        for item in selected:
            pid = int(self._tree.item(item)['values'][0])
            db.delete_paper(pid)
        db.invalidate_index()
        self._refresh_table()
        self._refresh_paper_count()
        self._db_status.config(text='تم الحذف بنجاح')

    def _refresh_table(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for p in db.get_all_papers():
            self._tree.insert('', 'end', values=(
                p['id'], p['title'],
                p.get('file_path', ''),
                str(p.get('added_at', ''))[:16]
            ))

    def _refresh_paper_count(self):
        count = db.get_paper_count()
        self._count_lbl.config(text=f'قاعدة البيانات: {count} بحث')

    # ──────────────────────────────────────────────────────────────────────────
    # فحص البحث الجديد
    # ──────────────────────────────────────────────────────────────────────────
    def _load_check_file(self):
        path = filedialog.askopenfilename(
            title='اختر البحث المراد فحصه',
            filetypes=[('ملفات مدعومة', '*.pdf *.docx *.doc *.txt')]
        )
        if not path:
            return
        text = extract_text(path)
        if not text.strip():
            messagebox.showerror('خطأ', 'تعذّر استخراج النص من الملف.')
            return
        self._input_text.delete('1.0', 'end')
        self._input_text.insert('1.0', text)
        self._check_status.config(text=f'تم تحميل: {os.path.basename(path)}')

    def _start_check(self):
        raw = self._input_text.get('1.0', 'end').strip()
        if not raw:
            messagebox.showwarning('تنبيه', 'الرجاء إدخال نص البحث أو تحميل ملف أولًا.')
            return
        if db.get_paper_count() == 0:
            messagebox.showwarning('تنبيه', 'قاعدة البيانات فارغة. أضف أبحاثًا أولًا.')
            return

        self._check_progress.start()
        self._check_status.config(text='جاري الفحص...')

        def worker():
            report = detector.analyze_text(raw)
            self.after(0, lambda: self._show_results(report))

        threading.Thread(target=worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────────
    # عرض النتائج
    # ──────────────────────────────────────────────────────────────────────────
    def _show_results(self, report: dict):
        self._check_progress.stop()
        self._check_status.config(text='اكتمل الفحص والتحليل بنجاح')
        self._last_report = report

        # بطاقات الإحصاء
        overall = report['overall_pct']
        self._stat_overall.config(text=f"{overall}%")
        self._stat_copied.config(text=f"{report['copied_pct']}%")
        self._stat_para.config(text=f"{report['paraphrase_pct']}%")
        original_pct = round(100 - overall, 1)
        self._stat_original.config(text=f"{original_pct}%")

        # النص الملوَّن
        rt = self._result_text
        rt.config(state='normal')
        rt.delete('1.0', 'end')
        rt.tag_config('copied',      background='#5c1a1a', foreground=RED_COPY)
        rt.tag_config('paraphrased', background='#4a3000', foreground=ORANGE_PAR)
        rt.tag_config('original',    foreground=TEXT_MAIN)

        for seg in report['segments']:
            status = seg['status']
            text   = seg['text'] + '  '
            tag    = status  # 'original' | 'copied' | 'paraphrased'
            rt.insert('end', text, tag)
            if status != 'original':
                src   = seg.get('source_title', '')
                match = seg.get('match_pct', 0)
                label = f'[{match}% ← {src}]  ' if src else f'[{match}%]  '
                rt.insert('end', label, tag)
            rt.insert('end', '\n')

        rt.config(state='disabled')

        # جدول المصادر
        for item in self._src_tree.get_children():
            self._src_tree.delete(item)
        for i, src in enumerate(report['sources'], 1):
            self._src_tree.insert('', 'end', values=(i, src['title'], f"{src['pct']}%"))

        # الانتقال لتبويب النتائج
        self._nb.select(2)

    # ──────────────────────────────────────────────────────────────────────────
    # حفظ التقرير HTML
    # ──────────────────────────────────────────────────────────────────────────
    def _save_report(self):
        if not self._last_report:
            messagebox.showwarning('تنبيه', 'لا يوجد تقرير لحفظه. ابدأ بفحص بحث أولًا.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.html',
            filetypes=[('HTML', '*.html')],
            title='حفظ التقرير'
        )
        if not path:
            return
        html = _generate_html_report(self._last_report)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        messagebox.showinfo('تم الحفظ', f'تم حفظ التقرير في:\n{path}')


def _generate_html_report(report: dict) -> str:
    segments_html = ''
    for seg in report['segments']:
        txt = seg['text'].replace('<', '&lt;').replace('>', '&gt;')
        # Wrap text with Unicode BiDi isolation: FSI (U+2068) ... PDI (U+2069)
        safe_txt = '\u2068' + txt + '\u2069'
        status = seg['status']
        if status == 'copied':
            src   = seg.get('source_title', '')
            match = seg.get('match_pct', 0)
            title = f'نسخ حرفي {match}% من: {src}'
            segments_html += (
                f'<mark class="copied" dir="auto" title="{title}">{safe_txt}</mark>'
                f'<sup class="ref">[{match}%]</sup> '
            )
        elif status == 'paraphrased':
            src   = seg.get('source_title', '')
            match = seg.get('match_pct', 0)
            title = f'إعادة صياغة {match}% من: {src}'
            segments_html += (
                f'<mark class="paraphrased" dir="auto" title="{title}">{safe_txt}</mark>'
                f'<sup class="ref">[{match}%]</sup> '
            )
        else:
            segments_html += f'<span dir="auto">{safe_txt}</span> '

    page_limit_alert = report.get('page_limit_alert', {})
    limit_banner_html = ''
    if page_limit_alert.get('has_limit_exceeded'):
        details_html = '<br>'.join(page_limit_alert.get('details', []))
        limit_banner_html = f'''
        <div style="background-color: #fffbeb; border: 1.5px solid #fcd34d; border-right: 6px solid #d97706; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px; color: #92400e;">
            <div style="font-weight: 800; font-size: 15px; margin-bottom: 4px; display:flex; align-items:center; gap:8px;"><svg style="width:20px; height:20px; stroke:#b45309; fill:none; stroke-width:2;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg><span>تنبيه تجاوز الحد الأقصى للاقتباس من مصدر واحد (أكثر من 5 صفحات)</span></div>
            <div style="font-size: 13px; font-weight: 600; color: #b45309; line-height: 1.6;">{details_html}</div>
        </div>
        '''

    sources_rows = ''
    for i, src in enumerate(report['sources'], 1):
        is_over = src.get('pages', 0) >= 5.0
        pages_txt = f"{src.get('pages', 0)} صفحة تقريباً ({src.get('words', 0):,} كلمة)" if 'pages' in src else '-'
        warning_tag = '<span style="color:#dc2626; font-weight:800; display:block; font-size:11px;">تجاوز 5 صفحات</span>' if is_over else ''
        sources_rows += (
            f'<tr style="{"background:#fff5f5;" if is_over else ""}">'
            f'<td>{i}</td>'
            f'<td style="font-weight:700;">{src["title"]}<span style="display:block; font-size:12px; color:#64748b; font-weight:normal;">المؤلف: {src.get("author", "غير محدد")}</span></td>'
            f'<td style="font-size:13px; font-weight:600;">{pages_txt}{warning_tag}</td>'
            f'<td class="pct" style="{"color:#dc2626;" if is_over else ""}">{src["pct"]}%</td>'
            f'</tr>'
        )

    overall = report.get('overall_pct', 0)
    copied = report.get('copied_pct', 0)
    para = report.get('paraphrase_pct', 0)
    orig = round(100 - overall, 1)
    title = report.get('title', 'تقرير كشف الاستلال العلمي')
    date_str = report.get('date', '')

    import base64
    logo_src = '/static/logo.png'
    logo_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'Police-Academy-College-of-Graduate-Studies.png')
    if os.path.exists(logo_file):
        try:
            with open(logo_file, 'rb') as f:
                logo_src = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
        except Exception:
            pass

    return f'''<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>تقرير كشف الاستلال العلمي - {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; font-family: "Cairo", "Segoe UI", Tahoma, sans-serif !important; }}
  body {{ background: #f4f6fb; color: #1e293b; margin: 0; padding: 30px; direction: rtl; line-height: 1.6; }}
  .paper-page {{ max-width: 900px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); position: relative; }}
  .paper-page::before {{ content: ""; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 440px; height: 440px; background-image: url("{logo_src}"); background-repeat: no-repeat; background-position: center; background-size: contain; opacity: 0.038; pointer-events: none; }}
  
  .header-bar {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f2b5c; padding-bottom: 16px; margin-bottom: 24px; }}
  .header-title {{ font-size: 19px; font-weight: 800; color: #0f2b5c; margin: 0; }}
  .header-sub {{ font-size: 13px; color: #64748b; font-weight: 600; }}
  
  .print-btn {{ background: #0f2b5c; color: white; border: none; padding: 8px 18px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 13px; }}
  .print-btn:hover {{ background: #163a7a; }}

  .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }}
  .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center; }}
  .stat-label {{ font-size: 12px; color: #64748b; font-weight: 700; margin-bottom: 4px; }}
  .stat-val {{ font-size: 24px; font-weight: 800; }}

  .overall-c {{ color: #dc2626; }}
  .copied-c  {{ color: #ef4444; }}
  .para-c    {{ color: #f97316; }}
  .orig-c    {{ color: #10b981; }}

  .text-box {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 24px; line-height: 2.2; font-size: 15px; margin-bottom: 28px; text-align: justify; unicode-bidi: plaintext; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; position: relative; }}
  .text-box span, .text-box mark {{ unicode-bidi: isolate; }}
  mark.copied      {{ background: #fee2e2; color: #991b1b; border-radius: 3px; padding: 2px 5px; font-weight: 500; }}
  mark.paraphrased {{ background: #ffedd5; color: #9a3412; border-radius: 3px; padding: 2px 5px; font-weight: 500; }}
  sup.ref {{ font-size: 10px; color: #64748b; font-weight: 700; }}

  td {{ unicode-bidi: plaintext; direction: auto; }}

  .section-h {{ font-size: 16px; font-weight: 700; color: #0f2b5c; margin-bottom: 12px; border-right: 4px solid #0f2b5c; padding-right: 10px; }}

  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
  th, td {{ padding: 12px 14px; border-bottom: 1px solid #e2e8f0; text-align: right; }}
  th {{ background: #f8fafc; color: #0f2b5c; font-weight: 700; }}
  td.pct {{ color: #dc2626; font-weight: 800; }}

  @media print {{
    body {{ background: white; padding: 0; }}
    .paper-page {{ border: none; box-shadow: none; padding: 0; width: 100%; }}
    .print-btn {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="paper-page">
  <div class="header-bar">
    <div style="display: flex; align-items: center; gap: 16px;">
      <img src="{logo_src}" style="height: 52px; width: auto; object-fit: contain;">
      <div>
        <div style="font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 2px;">أكاديمية الشرطة — كلية الدراسات العليا</div>
        <h1 class="header-title">تقرير كشف الاستلال العلمي والأكاديمي</h1>
        <div class="header-sub" style="margin-top: 2px;">العنوان: {title} | التاريخ: {date_str}</div>
      </div>
    </div>
    <button class="print-btn" onclick="window.print()">طباعة التقرير / PDF</button>
  </div>


  {limit_banner_html}

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">نسبة الاستلال الإجمالية</div><div class="stat-val overall-c">{overall}%</div></div>
    <div class="stat-card"><div class="stat-label">نسخ حرفي</div><div class="stat-val copied-c">{copied}%</div></div>
    <div class="stat-card"><div class="stat-label">إعادة صياغة</div><div class="stat-val para-c">{para}%</div></div>
    <div class="stat-card"><div class="stat-label">نص أصلي</div><div class="stat-val orig-c">{orig}%</div></div>
  </div>

  <div class="section-h">النص المحلل مع التظليل الأصلي</div>
  <div class="text-box">{segments_html}</div>

  <div class="section-h">جدول المصادر المكتشفة</div>
  <table>
    <thead>
      <tr><th>#</th><th>عنوان المصدر</th><th>الحجم المقتبس</th><th>نسبة التطابق</th></tr>
    </thead>
    <tbody>
      {sources_rows if sources_rows else '<tr><td colspan="4" style="text-align:center; color:#64748b;">لم يُكتشف أي تطابق</td></tr>'}
    </tbody>
  </table>
</div>
</body>
</html>'''



# ─────────────────────────────────────────────────────────────────────────────
def main():
    app = PlagiarismApp()
    app.mainloop()


if __name__ == '__main__':
    main()
