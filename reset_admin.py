# -*- coding: utf-8 -*-
"""
أداة استرجاع وتعيين بيانات مدير النظام (Admin Recovery Tool)
تتيح للمسؤول استرجاع أو إعادة تعيين اسم المستخدم وكلمة المرور من موجه الأوامر (CMD) بسهولة وأمان.
"""
import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

try:
    import bcrypt
except ImportError:
    print("[ERROR] bcrypt is required. Run: pip install bcrypt")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent

def get_database_paths():
    """البحث عن كافة مسارات قواعد البيانات الممكنة للنظام"""
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
        
    # 3. Project Root & Config
    try:
        sys.path.insert(0, str(ROOT))
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

def hash_password(password: str) -> str:
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

def list_users(db_path: Path):
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

def reset_admin_account(db_path: Path, username: str, new_password: str):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    pw_hash = hash_password(new_password)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        # Check if user exists
        existing = c.execute("SELECT id, username, role FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
        
        if existing:
            user_id = existing[0]
            c.execute("""
                UPDATE users 
                SET password_hash = ?, 
                    role = 'system_admin', 
                    is_active = 1,
                    must_change_password = 0,
                    must_enroll_recovery = 0
                WHERE id = ?
            """, (pw_hash, user_id))
            action = f"تم تحديث بيانات المستخدم القائم ({existing[1]})"
        else:
            c.execute("""
                INSERT INTO users (username, password_hash, full_name, role, is_active, must_change_password, must_enroll_recovery, session_version, created_at)
                VALUES (?, ?, ?, 'system_admin', 1, 0, 0, 1, ?)
            """, (username, pw_hash, f'مدير النظام ({username})', now_str))
            action = f"تم إنشاء حساب مسؤول جديد ({username})"

        # Clear failed login lockouts
        try:
            c.execute("UPDATE auth_lockouts SET failed_count = 0, locked_until = NULL, lockout_count = 0")
        except sqlite3.OperationalError:
            pass # Table might not exist in old schemas

        conn.commit()
        return True, action
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="أداة استرجاع وتعيين كلمة مرور مدير النظام")
    parser.add_argument("-u", "--user", default="admin", help="اسم المستخدم (الافتراضي: admin)")
    parser.add_argument("-p", "--password", default="Academic@2026#Secure", help="كلمة المرور الجديدة (الافتراضية: Academic@2026#Secure)")
    parser.add_argument("-l", "--list", action="store_true", help="عرض المستخدمين الحاليين دون تغيير")
    
    args = parser.parse_args()
    
    print("\n" + "="*65)
    print("      أكاديمية الشرطة — منظومة كشف الاستلال العلمي")
    print("             أداة استرجاع وتعيين حساب المدير")
    print("="*65)
    
    dbs = get_database_paths()
    if not dbs:
        print("\n[تحذير] لم يتم العثور على ملفات قاعدة بيانات نشطة على هذا الجهاز.")
        print("تأكد من تشغيل النظام لمرة واحدة على الأقل لتهيئة قاعدة البيانات.")
        return

    if args.list:
        for db in dbs:
            list_users(db)
        return

    print(f"\nجاري تعيين كلمة المرور للمستخدم: [{args.user}] ...")
    success_count = 0
    for db in dbs:
        ok, msg = reset_admin_account(db, args.user, args.password)
        # Also always reset Tamer Darwish if default admin was requested
        if args.user == "admin":
            reset_admin_account(db, "Tamer Darwish", args.password)
            
        if ok:
            success_count += 1
            print(f"  ✓ {db.name}: {msg}")
        else:
            print(f"  ✗ {db.name}: {msg}")

    if success_count > 0:
        print("\n" + "="*65)
        print("         ✓ تم تعيين بيانات الدخول بنجاح تام!")
        print("="*65)
        print(f"  اسم المستخدم (Username): {args.user}")
        if args.user == "admin":
            print(f"  اسم بديل صالح أيضاً    : Tamer Darwish")
        print(f"  كلمة المرور  (Password): {args.password}")
        print(f"  الرتبة / الصلاحية (Role): مدير النظام العام (system_admin)")
        print(f"  حالة الحساب             : مفعل (Active) وغير مقفل")
        print("="*65)
        print("\nيمكنك الآن تسجيل الدخول مباشرة في المنظومة بهذه البيانات.")
    else:
        print("\n[فشل] تعذر تحديث بيانات الحساب في قواعد البيانات.")

if __name__ == '__main__':
    main()
