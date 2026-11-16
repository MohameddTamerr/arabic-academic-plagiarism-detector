# -*- coding: utf-8 -*-
"""
أداة استرجاع وتعيين بيانات مدير النظام (Secure Admin Emergency Recovery Tool)
- تتطلب صلاحيات مسؤول نظام التشغيل Windows المرتفعة (Run as Administrator).
- تلزم بالتأكيد الصريح لمنع التغيير غير المصرح به.
- تمنع كلمات المرور الافتراضية المعروفة وتفرض كلمة مرور قوية جديدة.
- تقوم بتدوير مفتاح الاسترداد دون إنترنت (Offline Recovery Key) وعرضه مرة واحدة.
- توثق الحدث في سجل التدقيق المؤسسي.
"""
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.security.emergency_recovery import (
    is_windows_admin,
    perform_emergency_admin_reset,
    validate_new_recovery_password
)


def get_database_paths():
    """البحث عن كافة مسارات قواعد البيانات الممكنة للنظام"""
    import sqlite3

    def is_valid_db(p):
        try:
            conn = sqlite3.connect(str(p))
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            ok = bool(c.fetchone())
            conn.close()
            return ok
        except Exception:
            return False

    paths = []

    # 1. AppData Local (Standard Production Exe Path)
    p1 = Path.home() / 'AppData' / 'Local' / 'ArabicAcademicPlagiarismSystem' / 'Data' / 'Database' / 'papers.db'
    if p1.exists():
        paths.append(p1)

    # 2. AppData Roaming (Legacy / Fallback Exe Path)
    p2 = Path.home() / 'AppData' / 'Roaming' / 'ArabicPlagiarismDetector' / 'papers.db'
    if p2.exists():
        paths.append(p2)

    # 3. Project Config
    try:
        import config
        cfg_db = Path(config.DATABASE_PATH).resolve()
        if cfg_db.exists() and cfg_db not in paths:
            paths.append(cfg_db)
    except Exception:
        pass

    local_db = ROOT / 'papers.db'
    if local_db.exists() and local_db not in paths:
        paths.append(local_db)

    return [p for p in paths if is_valid_db(p)]


def list_users(db_path: Path):
    import sqlite3
    print(f"\n[قاعدة البيانات]: {db_path}")
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    try:
        users = c.execute("SELECT id, username, full_name, role, is_active FROM users").fetchall()
        if not users:
            print("  لا يوجد مستخدمون مسجلون.")
        else:
            print("  المستخدمون الحاليون في النظام:")
            for u in users:
                status = "نشط" if u[4] == 1 else "معطل"
                print(f"  - المعرف: {u[0]} | اسم المستخدم: {u[1]} | الاسم: {u[2]} | الصلاحية: {u[3]} | الحالة: {status}")
    except Exception as e:
        print(f"  خطأ أثناء قراءة المستخدمين: {e}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="أداة استرجاع وتعيين كلمة مرور مدير النظام المعتمدة")
    parser.add_argument("-u", "--user", default=None, help="اسم المستخدم (اختياري: سيتم تحديده تلقائياً من المدير القائم)")
    parser.add_argument("-p", "--password", default=None, help="كلمة المرور الجديدة القوية (سيُطلب إدخالها سرياً إن لم تُحدد)")
    parser.add_argument("-l", "--list", action="store_true", help="عرض المستخدمين الحاليين دون تغيير")
    parser.add_argument("--confirm", "--confirm-emergency-reset", dest="confirm", action="store_true", help="تأكيد صريح لتنفيذ الاسترداد الطارئ دون انتظار سؤال تفاعلي")
    parser.add_argument("--pin", default=None, help="رمز PIN الخاص ببطاقة الاسترداد (6 إلى 10 أرقام)")

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("      أكاديمية الشرطة — كلية الدراسات العليا")
    print("   منظومة كشف الاستلال العلمي — أداة الاسترداد الطارئ لحساب المدير")
    print("=" * 70)

    # 1. التحقق من صلاحيات مسؤول ويندوز
    if not is_windows_admin():
        print("\n[!] خطأ أمني: يتطلب إجراء الاسترداد الطارئ صلاحيات مسؤول نظام التشغيل Windows (Run as Administrator).")
        print("يرجى فتح موجه الأوامر (CMD أو PowerShell) كمسؤول (Run as administrator) ثم إعادة المحاولة.")
        sys.exit(5)

    dbs = get_database_paths()
    if not dbs:
        print("\n[تحذير] لم يتم العثور على ملفات قاعدة بيانات نشطة على هذا الجهاز.")
        print("تأكد من تشغيل النظام لمرة واحدة على الأقل لتهيئة قاعدة البيانات.")
        sys.exit(1)

    if args.list:
        for db in dbs:
            list_users(db)
        return

    success_data = None
    success_count = 0

    for db in dbs:
        ok, res_data, msg, err_code = perform_emergency_admin_reset(
            db_path=db,
            new_password=args.password,
            target_user=args.user,
            confirmed=args.confirm,
            interactive=True,
            recovery_pin=args.pin,
            bypass_elevation_for_test=False
        )
        if ok:
            success_count += 1
            success_data = res_data
            print(f"  ✓ {db.name}: تم التحديث بنجاح.")
        else:
            print(f"  ✗ {db.name}: {msg}")
            if err_code in ["ACCESS_DENIED", "CONFIRMATION_REQUIRED", "PASSWORD_TOO_WEAK", "CANCELLED"]:
                sys.exit(1)

    if success_count > 0 and success_data:
        print("\n" + "=" * 70)
        print("         ✓ تم استرداد وتعيين بيانات مدير المنظومة بنجاح تام!")
        print("=" * 70)
        print(f"  اسم المستخدم (Username) : {success_data['username']}")
        print(f"  الاسم الكامل            : {success_data['full_name']}")
        print("  حالة كلمة المرور        : تم التحديث وإلغاء صلاحية الجلسات السابقة فوراً")
        print("  ----------------------------------------------------------------------")
        print("  [مفتاح استرداد الحساب دون إنترنت البديل الجديد]:")
        print(f"  رمز الاسترداد المكتبي   : {success_data['manual_recovery_code']}")
        print(f"  رمز PIN لبطاقة الاسترداد: {success_data['recovery_pin']}")
        print("  ----------------------------------------------------------------------")
        print("  * يرجى تدوين هذا الرمز وحفظه في خزنة المؤسسة لاستخدامه في الطوارئ.")
        print(f"  * مسؤول نظام التشغيل المنفّذ: {success_data['os_user']}")
        print("=" * 70 + "\n")
    else:
        print("\n[فشل] تعذر إتمام الاسترداد الطارئ لحساب المدير.")
        sys.exit(1)


if __name__ == '__main__':
    main()
