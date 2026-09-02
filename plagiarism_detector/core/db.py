# -*- coding: utf-8 -*-
"""
إدارة قاعدة البيانات المحلية (SQLite).
- تخزين بيانات الأبحاث المصدرية (العنوان + النص الكامل)
- تخزين واسترجاع الفهرس المبني للكشف
"""

import sqlite3
import pickle
import os
import logging
import datetime
import hashlib
from pathlib import Path

from contextlib import contextmanager

logger = logging.getLogger(__name__)

# مجلد الملفات الخاصة بالتطبيق
_APP_DIR = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'ArabicPlagiarismDetector'
_DB_PATH = _APP_DIR / 'papers.db'
_INDEX_PATH = _APP_DIR / 'index.pkl'


def _ensure_dir():
    _APP_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    _ensure_dir()
    conn = sqlite3.connect(str(_DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL;')
    conn.execute('PRAGMA synchronous = NORMAL;')
    conn.execute('PRAGMA busy_timeout = 10000;')
    conn.execute('PRAGMA cache_size = -64000;')  # 64 MB in-memory cache
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _hash_password(password: str) -> str:
    """تشفير كلمة المرور أوفلاين باستخدام SHA-256 مع ملح ثابت."""
    import hashlib
    salt = "police_academy_grad_studies_2026_offline_salt"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()


def init_db():
    """يُنشئ جداول قاعدة البيانات وينفّذ التحديثات التلقائية الهيكلية والمستخدمين."""
    with get_connection() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS papers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                author      TEXT DEFAULT '',
                file_path   TEXT,
                full_text   TEXT NOT NULL,
                category    TEXT DEFAULT 'عام',
                added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);

            CREATE TABLE IF NOT EXISTS reports (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                author          TEXT DEFAULT '',
                overall_pct     REAL NOT NULL,
                copied_pct      REAL NOT NULL,
                para_pct        REAL NOT NULL,
                category        TEXT DEFAULT 'عام',
                status          TEXT DEFAULT 'محفوظ',
                file_path       TEXT DEFAULT '',
                submitted_by    TEXT DEFAULT '',
                submitted_notes TEXT DEFAULT '',
                report_json     TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name     TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'employee',
                reset_allowed INTEGER DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT NOT NULL,
                full_name   TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # التحديث التلقائي للجداول القديمة إن كانت موجودة بدون الأعمدة الجديدة
        for table, col in [('users', 'reset_allowed INTEGER DEFAULT 0'),
                           ('papers', "category TEXT DEFAULT 'عام'"),
                           ('papers', "author TEXT DEFAULT ''"),
                           ('reports', "category TEXT DEFAULT 'عام'"),
                           ('reports', "status TEXT DEFAULT 'محفوظ'"),
                           ('reports', "author TEXT DEFAULT ''"),
                           ('reports', "file_path TEXT DEFAULT ''"),
                           ('reports', "submitted_by TEXT DEFAULT ''"),
                           ('reports', "submitted_notes TEXT DEFAULT ''"),
                           ('password_reset_requests', "new_password_hash TEXT DEFAULT ''")]:
            try:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {col}')
            except sqlite3.OperationalError:
                pass  # العمود موجود بالفعل

        # إنشاء حساب مدير النظام الافتراضي إن لم يكن موجوداً
        admin_row = conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER('Tamer Darwish')").fetchone()
        if not admin_row:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                ('Tamer Darwish', _hash_password('Tamer@1978'), 'أ.د. تامر درويش (مدير النظام)', 'admin')
            )


def authenticate_user(username: str, password: str) -> dict | None:
    """التحقق من بيانات الدخول أوفلاين بالكامل."""
    if not username or not password:
        return None
    p_hash = _hash_password(password)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, full_name, role FROM users WHERE LOWER(username) = LOWER(?) AND password_hash = ?",
            (username.strip(), p_hash)
        ).fetchone()
        if row:
            return dict(row)
    return None


def authenticate_or_reset_user(username: str, password: str) -> tuple[dict | None, bool]:
    """التحقق من بيانات الدخول أوفلاين بالكامل مع دعم اعتماد كلمة المرور الجديدة عند موافقة المدير."""
    if not username or not password:
        return None, False
    username_clean = username.strip()
    p_hash = _hash_password(password)

    try:
        with get_connection() as conn:
            # 1. فحص الدخول العادي
            row = conn.execute(
                "SELECT id, username, full_name, role FROM users WHERE LOWER(username) = LOWER(?) AND password_hash = ?",
                (username_clean, p_hash)
            ).fetchone()
            if row:
                return {
                    'id': row['id'],
                    'username': row['username'],
                    'full_name': row['full_name'],
                    'role': row['role']
                }, False

            # 2. فحص إن كان هناك طلب معتمد أو تصريح بتعيين كلمة المرور الجديدة
            user_row = conn.execute(
                "SELECT id, username, full_name, role, reset_allowed FROM users WHERE LOWER(username) = LOWER(?)",
                (username_clean,)
            ).fetchone()

            if user_row and user_row['reset_allowed'] == 1:
                conn.execute(
                    "UPDATE users SET password_hash = ?, reset_allowed = 0 WHERE id = ?",
                    (p_hash, user_row['id'])
                )
                conn.execute(
                    "UPDATE password_reset_requests SET status = 'completed' WHERE user_id = ? AND status = 'approved'",
                    (user_row['id'],)
                )
                return {
                    'id': user_row['id'],
                    'username': user_row['username'],
                    'full_name': user_row['full_name'],
                    'role': user_row['role']
                }, True
    except Exception as e:
        logger.error(f"Authentication error: {e}")

    return None, False


def add_user(username: str, password: str, full_name: str, role: str = 'employee') -> tuple[bool, str]:
    """إضافة حساب موظف جديد أوفلاين بواسطة مدير النظام."""
    username = username.strip().lower()
    full_name = full_name.strip()
    if not username or not password or not full_name:
        return False, 'جميع الحقول مطلوبة'
    if len(password) < 4:
        return False, 'كلمة المرور يجب ألا تقل عن 4 خانات'
    
    p_hash = _hash_password(password)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, p_hash, full_name, role)
            )
            return True, 'تمت إضافة الحساب بنجاح'
    except sqlite3.IntegrityError:
        return False, 'اسم المستخدم مستخدم بالفعل، اختر اسم مستخدم آخر'
    except Exception as e:
        return False, str(e)


def get_users_list() -> list[dict]:
    """استرجاع قائمة كافة الموظفين والمستخدمين."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, created_at FROM users ORDER BY role ASC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_user(user_id: int) -> tuple[bool, str]:
    """حذف حساب موظف (لا يمكن حذف حساب المدير الرئيسي)."""
    with get_connection() as conn:
        user = conn.execute("SELECT username, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 'المستخدم غير موجود'
        if user['username'] == 'admin':
            return False, 'لا يمكن حذف حساب المدير الرئيسي للنظام'
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True, 'تم حذف الحساب بنجاح'


def change_password(username: str, old_pass: str, new_pass: str) -> bool:
    """تغيير كلمة المرور للمستخدم."""
    user = authenticate_user(username, old_pass)
    if not user:
        return False
    new_hash = _hash_password(new_pass)
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username.strip().lower()))
        return True


def admin_reset_user_password(user_id: int, new_pass: str) -> tuple[bool, str]:
    """إعادة تعيين كلمة مرور موظف بواسطة مدير النظام."""
    if len(new_pass) < 4:
        return False, 'كلمة المرور الجديدة يجب ألا تقل عن 4 خانات'
    new_hash = _hash_password(new_pass)
    with get_connection() as conn:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        if cur.rowcount > 0:
            return True, 'تمت إعادة تعيين كلمة المرور بنجاح'
        return False, 'المستخدم غير موجود'


_MASTER_RECOVERY_KEY = 'POLICE-ACADEMY-2026'

def reset_admin_with_master_key(master_key: str, new_pass: str) -> tuple[bool, str]:
    """استعادة كلمة مرور مدير النظام في حالات الطوارئ باستخدام مفتاح الأمان الرئيسي."""
    if master_key.strip() != _MASTER_RECOVERY_KEY:
        return False, 'مفتاح الأمان الرئيسي للطوارئ غير صحيح'
    if len(new_pass) < 4:
        return False, 'كلمة المرور الجديدة يجب ألا تقل عن 4 خانات'
    new_hash = _hash_password(new_pass)
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (new_hash,))
        return True, 'تمت استعادة وتعيين كلمة مرور مدير النظام بنجاح'



def create_database_backup() -> str:
    """إنشاء نسخة احتياطية فورية من قاعدة البيانات على القرص مع الاحتفاظ بآخر 20 نسخة."""
    _ensure_dir()
    backup_dir = _APP_DIR / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f'papers_backup_{now_str}.db'
    src_conn = sqlite3.connect(str(_DB_PATH), timeout=30.0)
    dst_conn = sqlite3.connect(str(backup_file))
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    # تنظيف تلقائي للنسخ القديمة للاحتفاظ بآخر 20 نسخة فقط للحفاظ على المساحة
    try:
        all_backups = sorted(list(backup_dir.glob('*.db')), key=lambda f: f.stat().st_mtime, reverse=True)
        if len(all_backups) > 20:
            for old_f in all_backups[20:]:
                try:
                    old_f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    return str(backup_file)


def auto_backup_if_needed():
    """ينشئ نسخة احتياطية تلقائية دورية إذا مضى أكثر من 6 ساعات على آخر نسخة."""
    try:
        backups = get_backups_list()
        now_ts = datetime.datetime.now().timestamp()
        if not backups:
            create_database_backup()
            return
        latest_time = datetime.datetime.strptime(backups[0]['created_at'], '%Y-%m-%d %H:%M:%S').timestamp()
        if (now_ts - latest_time) > (3600 * 6):
            create_database_backup()
    except Exception as e:
        logger.debug(f"Auto backup check note: {e}")


def get_backups_list() -> list[dict]:
    """استرجاع قائمة النسخ الاحتياطية المتوفرة."""
    backup_dir = _APP_DIR / 'backups'
    if not backup_dir.exists():
        return []
    res = []
    for f in backup_dir.glob('*.db'):
        stat = f.stat()
        res.append({
            'filename': f.name,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'created_at': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        })
    res.sort(key=lambda x: x['created_at'], reverse=True)
    return res


def add_paper(title: str, full_text: str, file_path: str = '', category: str = 'عام', author: str = '') -> int:
    """
    يضيف بحثًا جديدًا إلى قاعدة البيانات الأساسية للمقارنة.
    يرجع id البحث المضاف.
    """
    from plagiarism_detector.core.normalize import clean_arabic_display_text
    title = clean_arabic_display_text(title)
    author = clean_arabic_display_text(author)
    auto_backup_if_needed()
    with get_connection() as conn:
        cur = conn.execute(
            'INSERT INTO papers (title, author, full_text, file_path, category) VALUES (?, ?, ?, ?, ?)',
            (title, author, full_text, file_path, category)
        )
        return cur.lastrowid


def paper_exists(title: str) -> bool:
    """يتحقق من وجود بحث بنفس العنوان."""
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM papers WHERE title = ?', (title,)).fetchone()
        return row is not None


def delete_paper(paper_id: int):
    """يحذف بحثًا من قاعدة البيانات."""
    with get_connection() as conn:
        conn.execute('DELETE FROM papers WHERE id = ?', (paper_id,))


def update_paper(paper_id: int, title: str = None, author: str = None, category: str = None, added_at: str = None):
    """تعديل بيانات بحث مرجعي في قاعدة البيانات بما في ذلك التاريخ."""
    from plagiarism_detector.core.normalize import clean_arabic_display_text
    with get_connection() as conn:
        if title is not None:
            conn.execute('UPDATE papers SET title = ? WHERE id = ?', (clean_arabic_display_text(title), paper_id))
        if author is not None:
            conn.execute('UPDATE papers SET author = ? WHERE id = ?', (clean_arabic_display_text(author), paper_id))
        if category is not None:
            conn.execute('UPDATE papers SET category = ? WHERE id = ?', (clean_arabic_display_text(category), paper_id))
        if added_at is not None and added_at.strip():
            conn.execute('UPDATE papers SET added_at = ? WHERE id = ?', (added_at.strip(), paper_id))


def get_all_papers() -> list[dict]:
    """يرجع قائمة بكل الأبحاث الأساسية (بدون النص الكامل)."""
    with get_connection() as conn:
        rows = conn.execute('SELECT id, title, author, category, file_path, added_at FROM papers ORDER BY added_at DESC').fetchall()
        return [dict(r) for r in rows]


def get_all_papers_full() -> list[dict]:
    """يرجع كل الأبحاث مع النص الكامل (لالفهرسة)."""
    with get_connection() as conn:
        rows = conn.execute('SELECT id, title, author, full_text FROM papers').fetchall()
        return [dict(r) for r in rows]


def get_paper_count() -> int:
    with get_connection() as conn:
        return conn.execute('SELECT COUNT(*) FROM papers').fetchone()[0]


def save_report_db(report_id: str, title: str, overall_pct: float, copied_pct: float, para_pct: float, report_dict: dict, category: str = 'عام', status: str = 'محفوظ', author: str = '', file_path: str = ''):
    """حفظ التقرير في قاعدة البيانات."""
    import json
    with get_connection() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO reports (id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, report_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (report_id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, json.dumps(report_dict, ensure_ascii=False))
        )


def set_report_status(report_id: str, status: str):
    """تحديث حالة التقرير (مثل: قبول مبدئي، قبول نهائي)."""
    import json
    with get_connection() as conn:
        row = conn.execute('SELECT report_json FROM reports WHERE id = ?', (report_id,)).fetchone()
        if row:
            report_dict = json.loads(row[0])
            report_dict['status'] = status
            conn.execute(
                'UPDATE reports SET status = ?, report_json = ? WHERE id = ?',
                (status, json.dumps(report_dict, ensure_ascii=False), report_id)
            )


def submit_report_to_admin(report_id: str, employee_name: str, notes: str = ''):
    """إرسال البحث من قبل الموظف لمدير النظام للاعتماد والفحص الأولي."""
    import json
    with get_connection() as conn:
        row = conn.execute('SELECT report_json FROM reports WHERE id = ?', (report_id,)).fetchone()
        if row:
            report_dict = json.loads(row[0])
            report_dict['status'] = 'بانتظار الفحص الأولي'
            report_dict['submitted_by'] = employee_name
            report_dict['submitted_notes'] = notes
            conn.execute(
                'UPDATE reports SET status = ?, submitted_by = ?, submitted_notes = ?, report_json = ? WHERE id = ?',
                ('بانتظار الفحص الأولي', employee_name, notes, json.dumps(report_dict, ensure_ascii=False), report_id)
            )


def get_pending_initial_reviews_db(search_query: str = '') -> list[dict]:
    """استرجاع كافة الأبحاث المرسلة من الموظفين بانتظار الفحص الأولي وقرار المدير."""
    import json
    with get_connection() as conn:
        if search_query:
            q = f"%{search_query.strip()}%"
            rows = conn.execute(
                '''SELECT id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, submitted_by, submitted_notes, created_at, report_json 
                   FROM reports 
                   WHERE status = 'بانتظار الفحص الأولي' AND (title LIKE ? OR author LIKE ? OR submitted_by LIKE ?) 
                   ORDER BY created_at DESC''',
                (q, q, q)
            ).fetchall()
        else:
            rows = conn.execute(
                '''SELECT id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, submitted_by, submitted_notes, created_at, report_json 
                   FROM reports 
                   WHERE status = 'بانتظار الفحص الأولي' 
                   ORDER BY created_at DESC'''
            ).fetchall()
        
        result = []
        for r in rows:
            item = dict(r)
            try:
                item['report_json'] = json.loads(r['report_json'])
            except Exception:
                item['report_json'] = {}
            result.append(item)
        return result


def get_pending_initial_reviews_count() -> int:
    """استرجاع عدد الأبحاث المرسلة من الموظفين بانتظار قرار الفحص الأولي."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'بانتظار الفحص الأولي'").fetchone()
        return row[0] if row else 0


def get_preliminary_reports() -> list[dict]:
    """استرجاع كل الأبحاث التي تم قبولها مبدئياً."""
    import json
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, submitted_by, created_at, report_json FROM reports WHERE status = ? ORDER BY created_at DESC',
            ('قبول مبدئي',)
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item['report_json'] = json.loads(r['report_json'])
            except Exception:
                item['report_json'] = {}
            result.append(item)
        return result


def get_rejected_reports() -> list[dict]:
    """استرجاع كل الأبحاث والباحثين المرفوضين."""
    import json
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT id, title, author, overall_pct, copied_pct, para_pct, category, status, file_path, submitted_by, created_at, report_json FROM reports WHERE status = ? ORDER BY created_at DESC',
            ('مرفوض',)
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item['report_json'] = json.loads(r['report_json'])
            except Exception:
                item['report_json'] = {}
            result.append(item)
        return result



def delete_report_db(report_id: str):
    """حذف تقرير نهائياً من قاعدة البيانات."""
    with get_connection() as conn:
        conn.execute('DELETE FROM reports WHERE id = ?', (report_id,))


def update_report_latest_pdf(report_id: str, file_path: str, full_text: str = ''):
    """تحديث المسار والتقرير بالملف النهائي المحدث الأخير."""
    import json
    with get_connection() as conn:
        row = conn.execute('SELECT report_json FROM reports WHERE id = ?', (report_id,)).fetchone()
        if row:
            report_dict = json.loads(row[0])
            report_dict['final_file_path'] = file_path
            if full_text:
                report_dict['final_full_text'] = full_text
            conn.execute(
                'UPDATE reports SET file_path = ?, report_json = ? WHERE id = ?',
                (file_path, json.dumps(report_dict, ensure_ascii=False), report_id)
            )


def get_report_db(report_id: str) -> dict | None:
    """استرجاع تقرير محدد برقم المعرف."""
    import json
    with get_connection() as conn:
        row = conn.execute('SELECT report_json, status, author, file_path FROM reports WHERE id = ?', (report_id,)).fetchone()
        if row:
            res = json.loads(row['report_json'])
            res['status'] = row['status']
            res['author'] = row['author'] or res.get('author', '')
            res['file_path'] = row['file_path'] or res.get('file_path', '')
            return res
        return None


def get_recent_reports_db(limit: int = 10) -> list[dict]:
    """استرجاع قائمة بأحدث التقارير المحفوظة."""
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT id, title, author, status, overall_pct, copied_pct, para_pct, created_at FROM reports ORDER BY created_at DESC LIMIT ?',
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_reports_stats_db() -> dict:
    """استرجاع الإحصائيات العامة للتقارير."""
    with get_connection() as conn:
        total = conn.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
        avg = conn.execute('SELECT AVG(overall_pct) FROM reports').fetchone()[0] or 0.0
        preliminary_count = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'قبول مبدئي'").fetchone()[0]
        final_count = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'قبول نهائي'").fetchone()[0]
        pending_count = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'بانتظار الفحص الأولي'").fetchone()[0]
        return {
            'total_scans': total,
            'avg_plagiarism': round(avg, 1),
            'preliminary_count': preliminary_count,
            'final_count': final_count,
            'pending_initial_count': pending_count
        }



def save_index(index_obj: dict):
    """يحفظ الفهرس المبني على القرص كملف pickle."""
    _ensure_dir()
    with open(str(_INDEX_PATH), 'wb') as f:
        pickle.dump(index_obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_index() -> dict | None:
    """يحمّل الفهرس من القرص. يرجع None لو الفهرس غير موجود."""
    if not _INDEX_PATH.exists():
        return None
    try:
        with open(str(_INDEX_PATH), 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        logger.error(f"خطأ في تحميل الفهرس: {e}")
        return None


def invalidate_index():
    """يحذف الفهرس المحفوظ (يُستدعى بعد إضافة/حذف أبحاث)."""
    if _INDEX_PATH.exists():
        _INDEX_PATH.unlink()


def clear_all_data():
    """حذف جميع الأبحاث والتقارير والأرشيف والفهرس بالكامل من قاعدة البيانات."""
    with get_connection() as conn:
        conn.execute('DELETE FROM papers')
        conn.execute('DELETE FROM reports')
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=30.0)
        conn.isolation_level = None
        conn.execute('VACUUM')
        conn.close()
    except Exception:
        pass
    invalidate_index()




def request_password_reset(username: str, new_password: str = '') -> tuple[bool, str]:
    username = username.strip().lower()
    new_password = new_password.strip()
    if not username:
        return False, "الرجاء إدخال اسم المستخدم"
    if not new_password:
        return False, "الرجاء إدخال كلمة المرور الجديدة المطلوبة"
    if len(new_password) < 4:
        return False, "كلمة المرور يجب أن لا تقل عن 4 خانات"

    new_hash = _hash_password(new_password)

    with get_connection() as conn:
        user = conn.execute("SELECT id, username, full_name, role FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            return False, "اسم المستخدم غير مسجل في النظام"
        if user["role"] == "admin":
            return False, "حساب مدير النظام يتم استعادته حصراً عبر مفتاح الأمان الرئيسي للطوارئ"

        existing = conn.execute("SELECT id FROM password_reset_requests WHERE username = ? AND status = 'pending'", (username,)).fetchone()
        if existing:
            conn.execute("UPDATE password_reset_requests SET new_password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_hash, existing["id"]))
            return True, "تم تحديث طلبك وإرسال كلمة المرور الجديدة لمدير النظام للاعتماد"

        conn.execute(
            "INSERT INTO password_reset_requests (user_id, username, full_name, new_password_hash, status) VALUES (?, ?, ?, ?, 'pending')",
            (user["id"], username, user["full_name"], new_hash)
        )
        return True, f"تم إرسال طلب تعيين كلمة المرور للمدير بنجاح للموظف ({user['full_name']}). فور موافقة المدير يمكنك تسجيل الدخول بها فوراً."

        conn.execute(
            "INSERT INTO password_reset_requests (user_id, username, full_name, status) VALUES (?, ?, ?, 'pending')",
            (user["id"], username, user["full_name"])
        )
        return True, "تم إرسال الطلب لمدير النظام بنجاح. بمجرد موافقة المدير، قم بكتابة اسم المستخدم وكلمة المرور الجديدة في شاشة الدخول وسيتم حفظها وتفعيلها فوراً."


def get_password_reset_requests() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, user_id, username, full_name, status, created_at, updated_at FROM password_reset_requests ORDER BY (status = 'pending') DESC, created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]


def approve_password_reset(request_id: int) -> tuple[bool, str]:
    with get_connection() as conn:
        req = conn.execute("SELECT user_id, username, full_name, new_password_hash FROM password_reset_requests WHERE id = ?", (request_id,)).fetchone()
        if not req:
            return False, "الطلب غير موجود"
        
        # إذا كان الموظف أرسل كلمة المرور الجديدة مع الطلب
        if req["new_password_hash"]:
            conn.execute("UPDATE users SET password_hash = ?, reset_allowed = 0 WHERE id = ?", (req["new_password_hash"], req["user_id"]))
            conn.execute("UPDATE password_reset_requests SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
            return True, f"تم اعتماد وتعيين كلمة المرور الجديدة بنجاح للموظف ({req['full_name']}). يمكنه الآن تسجيل الدخول بها فوراً."
        else:
            conn.execute("UPDATE password_reset_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
            conn.execute("UPDATE users SET reset_allowed = 1 WHERE id = ?", (req["user_id"],))
            return True, f"تمت الموافقة بنجاح على طلب الموظف ({req['full_name']}). يمكنه الآن إدخال كلمة المرور الجديدة مباشرة عند تسجيل الدخول."


def decline_password_reset(request_id: int) -> tuple[bool, str]:
    with get_connection() as conn:
        conn.execute("UPDATE password_reset_requests SET status = 'declined', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (request_id,))
        return True, "تم رفض طلب استعادة كلمة المرور"

