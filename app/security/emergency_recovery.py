# -*- coding: utf-8 -*-
"""
منظومة الاسترداد المحلي الطارئ لحساب مدير المنظومة (Windows Emergency Administrator Recovery):
- اشتراط التحقق من صلاحيات مسؤول نظام التشغيل Windows المرتفعة (Elevated Windows Administrator).
- رفض تنفيذ الاسترداد للمستخدمين العاديين غير المصرح لهم على مستوى نظام التشغيل.
- اشتراط تأكيد محلي صريح لمنع التنفيذ العرضي أو غير المصرح به.
- منع استخدام كلمات المرور الافتراضية المعروفة أو العامة وإلزام تعيين كلمة مرور قوية جديدة.
- تدوير مفتاح الاسترداد دون إنترنت (Offline Recovery Key) وإصدار مفتاح بديل وتوثيق الحدث في سجل التدقيق المؤسسي.
- عدم طباعة كلمات المرور أو الأسرار الخام في ملفات السجلات نهائياً.
"""

import os
import sys
import ctypes
import secrets
import sqlite3
import getpass
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

try:
    import bcrypt
except ImportError:
    bcrypt = None

try:
    import argon2
    _argon2_hasher = argon2.PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=1,
        hash_len=32,
        type=argon2.Type.ID
    )
except ImportError:
    _argon2_hasher = None

from app.security.password_policy import validate_password_strength

KNOWN_DEFAULT_PASSWORDS = {
    'academic@2026#secure',
    'academic@2026',
    'admin@123456',
    'admin123456',
    'admin123',
    'admin@123',
    'password123',
    'password',
    'admin',
    '123456',
    '12345678',
    'police2026',
    'academy2026',
    'police@2026'
}


def is_windows_admin() -> bool:
    """
    التحقق الصارم مما إذا كانت العملية الحالية تمتلك صلاحيات مسؤول نظام التشغيل المرتفعة:
    - على ويندوز: التحقق عبر ctypes.windll.shell32.IsUserAnAdmin().
    - على أنظمة شبيهة يونكس: التحقق من معرّف المستخدم الفعلي euid == 0.
    """
    if sys.platform != 'win32':
        return hasattr(os, 'geteuid') and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def hash_password_bcrypt(password: str) -> str:
    """تشفير كلمة المرور باستخدام bcrypt ومطابقة إعدادات المنظومة."""
    if bcrypt is None:
        raise RuntimeError("مكتبة bcrypt غير متوفرة لتشفير كلمة المرور.")
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def hash_secret_argon2(secret_value: str) -> str:
    """تجزئة السر باستخدام Argon2id لبطاقات الاسترداد."""
    if _argon2_hasher is not None:
        return _argon2_hasher.hash(secret_value)
    # بديل آمن بالملح باستخدام PBKDF2-HMAC-SHA256 في حال عدم توفر Argon2
    salt = secrets.token_bytes(16)
    kdf = hashlib.pbkdf2_hmac('sha256', secret_value.encode('utf-8'), salt, 100000)
    return f"$pbkdf2-sha256${salt.hex()}${kdf.hex()}"


def format_manual_code(secret_hex: str) -> str:
    """تنسيق السر الخام إلى رمز استرداد مقسم لمجموعات مقروءة."""
    upper_hex = secret_hex.upper()
    chunks = [upper_hex[i:i + 8] for i in range(0, len(upper_hex), 8)]
    return "-".join(chunks)


def validate_new_recovery_password(password: str, username: str = 'admin') -> Tuple[bool, str]:
    """
    التحقق الصارم من متانة كلمة المرور ومنع كلمات المرور الافتراضية المعروفة:
    - رفض أي كلمة مرور معروفة أو شائعة.
    - التحقق من سياسة متانة كلمات المرور المعتمدة بأكاديمية الشرطة.
    """
    if not password:
        return False, "كلمة المرور الجديدة مطلوبة ولا يمكن تركها فارغة."

    cleaned_pw = password.strip()
    if cleaned_pw.lower() in KNOWN_DEFAULT_PASSWORDS:
        return False, "محظور أمنياً: لا يمكن استخدام كلمة مرور افتراضية أو عامة سابقة. يجب اختيار كلمة مرور قوية وجديدة."

    is_valid, msg = validate_password_strength(cleaned_pw, username=username)
    if not is_valid:
        return False, f"كلمة المرور غير مطابقة للسياسة الأمنية: {msg}"

    return True, "كلمة المرور مطابقة للسياسة الأمنية."


def check_local_confirmation(confirmed_flag: bool = False, interactive: bool = True) -> bool:
    """
    التحقق من التأكيد المحلي الصريح:
    - عبر راية الأمر الصريحة --confirm أو --confirm-emergency-reset
    - أو عبر طلب الإدخال التفاعلي من المستخدم في الطرفية.
    """
    if confirmed_flag:
        return True

    if not interactive or not sys.stdin.isatty():
        return False

    print("\n" + "=" * 70)
    print(" [!] تحذير أمني عالي الأهمية:")
    print(" أنت على وشك تنفيذ استرداد محلي طارئ لحساب مدير المنظومة الأكاديمية.")
    print(" هذا الإجراء مخصص لحالات الطوارئ القصوى فقط عند فقدان كلمة المرور")
    print(" ومفتاح الاسترداد معاً، ويجب أن يتم فقط بواسطة المسؤول المصرح له.")
    print("=" * 70)

    try:
        prompt_text = "هل تؤكد رغبتك في استرداد وتعيين حساب المدير؟ (اكتب 'نعم' أو 'yes' للمتابعة): "
        ans = input(prompt_text).strip().lower()
        return ans in ['نعم', 'yes', 'y']
    except (EOFError, KeyboardInterrupt):
        return False


def perform_emergency_admin_reset(
    db_path: Path,
    new_password: Optional[str] = None,
    target_user: Optional[str] = None,
    confirmed: bool = False,
    interactive: bool = True,
    recovery_pin: Optional[str] = None,
    bypass_elevation_for_test: bool = False
) -> Tuple[bool, Dict[str, Any], str, Optional[str]]:
    """
    تنفيذ الاسترداد الطارئ لحساب مدير المنظومة:
    1. التحقق من صلاحيات مسؤول ويندوز المرتفعة.
    2. التحقق من التأكيد الصريح.
    3. التحقق من كلمة المرور الجديدة ورفض الكلمات الافتراضية.
    4. تحديث كلمة مرور حساب المدير القائم في قاعدة البيانات وتصفير أقفال الدخول.
    5. إبطال مفاتيح الاسترداد القديمة وتوليد مفتاح استرداد بديل جديد.
    6. توثيق الحدث في سجل التدقيق المؤسسي دون كشف الأسرار.
    """
    # 1. التحقق من صلاحيات مسؤول ويندوز المرتفعة
    if not bypass_elevation_for_test and not is_windows_admin():
        err_msg = (
            "خطأ أمني: يتطلب إجراء الاسترداد الطارئ لحساب المدير صلاحيات مسؤول نظام التشغيل Windows (Run as Administrator).\n"
            "يرجى تشغيل موجه الأوامر (CMD أو PowerShell) كمسؤول وإعادة المحاولة."
        )
        return False, {}, err_msg, "ACCESS_DENIED"

    # 2. التحقق من التأكيد الصريح
    if not check_local_confirmation(confirmed, interactive):
        err_msg = (
            "تم إلغاء عملية الاسترداد لعدم توفر التأكيد الصريح.\n"
            "في نمط الأتمتة أو سطر الأوامر غير التفاعلي، يجب تمرير الخيار: --confirm-emergency-reset"
        )
        return False, {}, err_msg, "CONFIRMATION_REQUIRED"

    # 3. استلام والتحقق من كلمة المرور الجديدة
    chosen_password = new_password
    if not chosen_password:
        if interactive and sys.stdin.isatty():
            try:
                p1 = getpass.getpass("أدخل كلمة المرور الجديدة لمدير المنظومة: ")
                p2 = getpass.getpass("تأكيد كلمة المرور الجديدة: ")
                if p1 != p2:
                    return False, {}, "كلمة المرور وتأكيدها غير متطابقين.", "PASSWORD_MISMATCH"
                chosen_password = p1
            except (EOFError, KeyboardInterrupt):
                return False, {}, "تم إلغاء إدخال كلمة المرور.", "CANCELLED"
        else:
            return False, {}, "يجب تمرير كلمة المرور الجديدة عبر: --password=\"YourStrongPassword\"", "PASSWORD_REQUIRED"

    is_pw_valid, pw_err = validate_new_recovery_password(chosen_password, username=target_user or 'admin')
    if not is_pw_valid:
        return False, {}, pw_err, "PASSWORD_TOO_WEAK"

    # التحقق من وجود قاعدة البيانات
    if not db_path.exists():
        return False, {}, f"ملف قاعدة البيانات غير موجود في المسار: {db_path}", "DB_NOT_FOUND"

    # 4. تحديث قاعدة البيانات
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    now_dt = datetime.utcnow()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    os_username = getpass.getuser()

    try:
        # البحث عن حساب المدير المستهدف أو الحساب الإداري الوحيد
        admin_row = None
        if target_user:
            c.execute("SELECT id, username, full_name, role, session_version FROM users WHERE LOWER(username) = LOWER(?)", (target_user.strip(),))
            admin_row = c.fetchone()

        if not admin_row:
            # البحث عن المدير القائم ذي أعلى صلاحية
            c.execute("SELECT id, username, full_name, role, session_version FROM users WHERE role IN ('system_admin', 'admin') ORDER BY id ASC LIMIT 1")
            admin_row = c.fetchone()

        pw_hash = hash_password_bcrypt(chosen_password)

        if admin_row:
            user_id, resolved_username, full_name, role, session_ver = admin_row
            new_session_ver = (session_ver or 1) + 1
            c.execute("""
                UPDATE users 
                SET password_hash = ?, 
                    role = 'system_admin', 
                    is_active = 1,
                    must_change_password = 0,
                    must_enroll_recovery = 0,
                    session_version = ?
                WHERE id = ?
            """, (pw_hash, new_session_ver, user_id))
        else:
            # إنشاء حساب المدير الأساسي إذا لم يكن موجوداً
            resolved_username = (target_user or 'admin').strip()
            full_name = f'مدير النظام ({resolved_username})'
            role = 'system_admin'
            new_session_ver = 1
            c.execute("""
                INSERT INTO users (username, password_hash, full_name, role, is_active, must_change_password, must_enroll_recovery, session_version, created_at)
                VALUES (?, ?, ?, 'system_admin', 1, 0, 0, 1, ?)
            """, (resolved_username, pw_hash, full_name, now_str))
            user_id = c.lastrowid

        # 5. إلغاء مفاتيح الاسترداد القديمة
        c.execute("""
            UPDATE account_recovery_credentials
            SET status = 'superseded', revoked_at = ?
            WHERE user_id = ? AND status = 'active'
        """, (now_str, user_id))

        # 6. توليد مفتاح استرداد بديل جديد بإنتروبيا 256 بت
        raw_secret_bytes = secrets.token_bytes(32)
        raw_secret_hex = raw_secret_bytes.hex()
        formatted_code = format_manual_code(raw_secret_hex)
        chosen_pin = recovery_pin.strip() if (recovery_pin and recovery_pin.strip().isdigit() and 6 <= len(recovery_pin.strip()) <= 10) else "123456"

        public_cred_id = f"RC-{now_dt.year}-{secrets.token_hex(6).upper()}"
        secret_verifier = hash_secret_argon2(raw_secret_hex)
        pin_verifier = hash_secret_argon2(chosen_pin)

        # التحقق من وجود جدول اعتمادات الاسترداد
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account_recovery_credentials'")
        if c.fetchone():
            c.execute("""
                INSERT INTO account_recovery_credentials 
                (user_id, credential_public_id, secret_verifier, pin_verifier, version, status, created_at, failure_count)
                VALUES (?, ?, ?, ?, 1, 'active', ?, 0)
            """, (user_id, public_cred_id, secret_verifier, pin_verifier, now_str))

        # تصفير أي قفل للدخول على الحساب
        try:
            user_ident = f"user_{resolved_username.lower()}"
            c.execute("UPDATE auth_lockouts SET failed_count = 0, locked_until = NULL, lockout_count = 0 WHERE identifier IN (?, ?)", (user_ident, resolved_username.lower()))
        except sqlite3.OperationalError:
            pass

        # 7. توثيق الحدث في سجل التدقيق المؤسسي
        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
            if c.fetchone():
                meta_json = f'{{"os_user": "{os_username}", "action": "windows_elevated_recovery", "credential_id": "{public_cred_id}", "timestamp": "{now_str}"}}'
                c.execute("""
                    INSERT INTO audit_logs (action, category, object_type, object_id, success, metadata, created_at)
                    VALUES ('auth.recovery.os_emergency_reset', 'security', 'user', ?, 1, ?, ?)
                """, (str(user_id), meta_json, now_str))
        except Exception:
            pass

        conn.commit()

        result_data = {
            "user_id": user_id,
            "username": resolved_username,
            "full_name": full_name,
            "credential_id": public_cred_id,
            "manual_recovery_code": formatted_code,
            "recovery_pin": chosen_pin,
            "os_user": os_username,
            "updated_at": now_str
        }

        success_msg = (
            "تم استرداد وتعيين بيانات مدير المنظومة بنجاح!\n"
            f"- اسم المستخدم (Username): {resolved_username}\n"
            "- تم تعيين كلمة المرور الجديدة وتحديث إصدار الجلسة.\n"
            f"- مفتاح الاسترداد البديل الجديد: {formatted_code}\n"
            f"- رمز PIN لبطاقة الاسترداد: {chosen_pin}\n"
            f"- مسؤول نظام التشغيل المنفّذ: {os_username}"
        )
        return True, result_data, success_msg, None

    except Exception as e:
        conn.rollback()
        return False, {}, f"حدث خطأ أثناء تحديث قاعدة البيانات: {str(e)}", "DB_ERROR"
    finally:
        conn.close()
