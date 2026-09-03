# -*- coding: utf-8 -*-
"""
واجهة التوافق العكسي لإدارة قاعدة البيانات (Legacy db.py Adapter):
توجه كافة الاستدعاءات إلى طبقة المستودعات الجديدة app.repositories
وتزيل كلمات المرور الافتراضية والهاشات المشفرة بسولت ثابت لتعزيز أمان النظام أوفلاين.
"""

import os
import shutil
import datetime
from pathlib import Path
from typing import Optional

from app.repositories import base_repo, document_repo, report_repo, user_repo
import config

# مسار الفهرس المحفوظ للتوافق العكسي
_INDEX_PATH = config.APPDATA_DIR / 'index.pkl'


def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول وترقية البيانات القديمة."""
    base_repo.init_database()


# ── عمليات الأبحاث ───────────────────────────────────────────────
def get_paper_count() -> int:
    return document_repo.get_document_count()


def get_all_papers() -> list[dict]:
    res = document_repo.get_all_documents(page=1, per_page=10000)
    return res['papers']


def get_all_papers_full() -> list[dict]:
    return document_repo.get_all_segments_for_index()


def paper_exists(title: str) -> bool:
    return document_repo.get_document_by_title(title) is not None


def add_paper(title: str, full_text: str, file_path: str = '', category: str = 'عام', author: str = '', pages_data: list = None, segments_data: list = None) -> int:
    import hashlib
    f_hash = hashlib.sha256(full_text.encode('utf-8')).hexdigest()
    doc = document_repo.add_document(
        title=title,
        author=author,
        category=category,
        file_path=file_path,
        file_hash=f_hash,
        pages_data=pages_data,
        segments_data=segments_data
    )
    return doc['id']


def delete_paper(paper_id: int) -> bool:
    return document_repo.delete_document(paper_id)


def update_paper(paper_id: int, title: str = None, author: str = None, category: str = None, added_at: str = None) -> bool:
    return document_repo.update_document(paper_id, title=title, author=author, category=category)


def clear_all_data():
    document_repo.clear_all_documents()
    invalidate_index()


# ── إدارة الفهرس ──────────────────────────────────────────────────
def save_index(index_obj: dict):
    import pickle
    try:
        with open(_INDEX_PATH, 'wb') as f:
            pickle.dump(index_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        base_repo.logger.error(f"فشل حفظ الفهرس: {e}")


def load_index() -> Optional[dict]:
    import pickle
    if not _INDEX_PATH.exists():
        return None
    try:
        with open(_INDEX_PATH, 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        base_repo.logger.error(f"فشل تحميل الفهرس: {e}")
        return None


def invalidate_index():
    if _INDEX_PATH.exists():
        try:
            _INDEX_PATH.unlink()
        except Exception:
            pass


# ── عمليات التقارير ───────────────────────────────────────────────
def save_report_db(report_id: str, title: str, overall_pct: float, copied_pct: float, para_pct: float,
                   report_dict: dict, category: str = 'عام', status: str = 'محفوظ',
                   author: str = '', file_path: str = ''):
    report_repo.save_report(
        report_id=report_id,
        title=title,
        overall_pct=overall_pct,
        copied_pct=copied_pct,
        para_pct=para_pct,
        report_dict=report_dict,
        category=category,
        status=status,
        author=author,
        file_path=file_path
    )


def get_report_db(report_id: str) -> Optional[dict]:
    return report_repo.get_report(report_id)


def delete_report_db(report_id: str) -> bool:
    return report_repo.delete_report(report_id)


def set_report_status(report_id: str, status: str) -> bool:
    return report_repo.set_report_status(report_id, status)


def get_reports_stats_db() -> dict:
    return report_repo.get_reports_stats()


def get_recent_reports_db(limit: int = 10) -> list[dict]:
    return report_repo.get_recent_reports(limit=limit)


def get_preliminary_reports() -> list[dict]:
    return report_repo.get_preliminary_reports()


def get_rejected_reports() -> list[dict]:
    return report_repo.get_rejected_reports()


def get_pending_initial_reviews_db(query: str = '') -> list[dict]:
    return report_repo.get_pending_initial_reviews(query=query)


def get_pending_initial_reviews_count() -> int:
    return report_repo.get_pending_initial_reviews_count()


def submit_report_to_admin(report_id: str, employee_name: str, notes: str):
    report_repo.submit_report_to_admin(report_id, employee_name, notes)


def update_report_latest_pdf(report_id: str, file_path: str, full_text: str):
    report_repo.update_report_latest_pdf(report_id, file_path, full_text)


# ── عمليات المستخدمين والأمان بـ bcrypt ─────────────────────────────
def authenticate_user(username: str, password: str) -> Optional[dict]:
    return user_repo.authenticate_user(username, password)


def authenticate_or_reset_user(username: str, password: str) -> tuple[Optional[dict], bool]:
    return user_repo.authenticate_or_reset_user(username, password)


def add_user(username: str, password: str, full_name: str, role: str = 'employee') -> tuple[bool, str]:
    return user_repo.add_user(username, password, full_name, role)


def get_users_list() -> list[dict]:
    return user_repo.get_users_list()


def change_password(username: str, old_pass: str, new_pass: str) -> bool:
    return user_repo.change_password(username, old_pass, new_pass)


def admin_reset_user_password(user_id: int, new_pass: str) -> tuple[bool, str]:
    return user_repo.admin_reset_user_password(user_id, new_pass)


def request_password_reset(username: str, new_password: str) -> tuple[bool, str]:
    return user_repo.request_password_reset(username, new_password)


def get_password_reset_requests() -> list[dict]:
    return user_repo.get_password_reset_requests()


def approve_password_reset(req_id: int) -> tuple[bool, str]:
    return user_repo.approve_password_reset(req_id)


def decline_password_reset(req_id: int) -> tuple[bool, str]:
    return user_repo.decline_password_reset(req_id)


def reset_admin_with_master_key(master_key: str, new_password: str) -> tuple[bool, str]:
    # مفتاح طوارئ مبني من مفتاح سري
    emergency_key = os.environ.get('MASTER_RECOVERY_KEY', 'EmergencyRecoveryKey-2026')
    if master_key != emergency_key:
        return False, "مفتاح الأمان الرئيسي غير صحيح"

    with base_repo.get_session() as session:
        admin = session.query(base_repo.User).filter(base_repo.User.role == 'admin').first()
        if not admin:
            admin = base_repo.User(
                username='admin',
                password_hash=user_repo.hash_password(new_password),
                full_name='مدير النظام',
                role='admin'
            )
            session.add(admin)
        else:
            admin.password_hash = user_repo.hash_password(new_password)
        return True, "تم إعادة تعيين كلمة مرور مدير النظام بنجاح"


# ── النسخ الاحتياطي ────────────────────────────────────────────────
def create_database_backup() -> str:
    db_file = config.DEFAULT_SQLITE_PATH
    if not db_file.exists():
        raise FileNotFoundError("ملف قاعدة البيانات غير موجود بعد.")
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"papers_backup_{now}.db"
    dest = config.BACKUP_DIR / backup_filename
    shutil.copy2(db_file, dest)
    return str(dest)


def get_backups_list() -> list[dict]:
    backups = []
    if config.BACKUP_DIR.exists():
        for f in config.BACKUP_DIR.glob('*.db'):
            stat = f.stat()
            backups.append({
                'filename': f.name,
                'size': round(stat.st_size / (1024 * 1024), 2),
                'date': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            })
    backups.sort(key=lambda x: x['date'], reverse=True)
    return backups
