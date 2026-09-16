# -*- coding: utf-8 -*-
"""
خدمة استرداد الحسابات بدون اتصال بالإنترنت (100% Offline QR Account Recovery Service):
- توليد بيانات اعتماد الاسترداد برمز مشفر ذي إنتروبيا 256 بت على الأقل.
- عدم تخزين السر الخام أو رمز PIN في قاعدة البيانات، والاعتماد حصرياً على مدققات Argon2id.
- دعم قراءة وفك تشفير رمز QR محلياً عبر OpenCV و PIL دون اتصال خارجي أو خدمات سحابية.
- إدارة معاملات الاسترداد المؤقتة ذات الاستخدام لمرة واحدة (10 دقائق صلاحية).
- كبح المحاولات الخاطئة والحماية ضد القوة الغاشمة وتوثيق كافة العمليات في سجل التدقيق المؤسسي.
"""

import io
import re
import json
import base64
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

import argon2
import qrcode
import cv2
import numpy as np
from PIL import Image

from app.models.schema import User, AccountRecoveryCredential, RecoveryTransaction, AuthLockout
from app.repositories.base_repo import get_session
from app.repositories.user_repo import hash_password, verify_password
from app.security.password_policy import validate_password_strength
from app.services import audit_service
from app.services.login_throttling_service import is_locked_out, record_failed_attempt, record_successful_login
from app.errors.error_codes import ErrorCode

logger = logging.getLogger(__name__)

# إعداد خوارزمية التجزئة الآمنة Argon2id
_argon2_hasher = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=1,
    hash_len=32,
    type=argon2.Type.ID
)

QR_PAYLOAD_TYPE = "AAPD_ACCOUNT_RECOVERY"
QR_PAYLOAD_VERSION = 1


def _hash_argon2(secret_value: str) -> str:
    """تجزئة القيمة النصية باستخدام Argon2id."""
    return _argon2_hasher.hash(secret_value)


def _verify_argon2(stored_hash: str, secret_value: str) -> bool:
    """التحقق من مطابقة القيمة للهاش المخزن باستخدام Argon2id."""
    if not stored_hash or not secret_value:
        return False
    try:
        return _argon2_hasher.verify(stored_hash, secret_value)
    except Exception:
        return False


def format_manual_code(secret_hex: str) -> str:
    """تنسيق السر الخام إلى رمز استرداد يدوي مقسم لمجموعات مقروءة."""
    upper_hex = secret_hex.upper()
    chunks = [upper_hex[i:i + 8] for i in range(0, len(upper_hex), 8)]
    return "-".join(chunks)


def normalize_manual_code(raw_code: str) -> str:
    """تنظيف وتوحيد مدخلات رمز الاسترداد اليدوي."""
    if not raw_code:
        return ""
    # إزالة المسافات والشرطات والرموز غير الأبجدية الرقمية
    cleaned = re.sub(r'[\s\-_\.:]', '', raw_code.strip())
    return cleaned.lower()


def generate_qr_image_base64(payload_dict: dict) -> str:
    """توليد صورة رمز QR كبيانات Base64 Data URI محلياً."""
    payload_str = json.dumps(payload_dict, ensure_ascii=False, separators=(',', ':'))
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(payload_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f2b5c", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_data = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/png;base64,{b64_data}"


def decode_qr_from_bytes(image_bytes: bytes) -> Tuple[bool, Optional[dict], str]:
    """
    فك تشفير رمز QR من مصفوفة بايتات الصورة محلياً باستخدام OpenCV و PIL.
    تتم المعالجة بالكامل في الذاكرة دون حفظ ملفات على القرص.
    """
    if not image_bytes or len(image_bytes) < 10:
        return False, None, "حجم ملف الصورة غير صالح"

    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        decoded_text = ""

        if img_cv is not None:
            detectors = [cv2.QRCodeDetector()]
            if hasattr(cv2, 'QRCodeDetectorAruco'):
                try:
                    detectors.append(cv2.QRCodeDetectorAruco())
                except Exception:
                    pass

            # محاولات متعددة لفك التشفير مع تحسينات التباين والحدود والقياس
            candidate_images = [img_cv]

            # إضافة إطار أبيض (Quiet Zone Padding)
            padded = cv2.copyMakeBorder(img_cv, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            candidate_images.append(padded)

            # التدرج الرمادي والعتبة الثنائية
            gray = cv2.cvtColor(padded, cv2.COLOR_BGR2GRAY)
            candidate_images.append(gray)
            _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            candidate_images.append(thresh)

            # تكبير الصورة للأكواد الكثيفة
            scaled = cv2.resize(padded, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_NEAREST)
            candidate_images.append(scaled)

            for cand in candidate_images:
                if decoded_text:
                    break
                for det in detectors:
                    try:
                        val, pts, _ = det.detectAndDecode(cand)
                        if val and val.strip():
                            decoded_text = val.strip()
                            break
                    except Exception:
                        pass

        # التحقق من النص المفكوك
        if not decoded_text:
            return False, None, "لم يتم العثور على رمز QR صالح في الصورة المحددة"

        try:
            payload = json.loads(decoded_text)
            if not isinstance(payload, dict):
                return False, None, "تنسيق بيانات رمز QR غير صالح"
            return True, payload, "تم فك تشفير رمز QR بنجاح"
        except Exception:
            return False, None, "بيانات رمز QR ليست بالتنسيق القياسي المعتمد"

    except Exception as e:
        logger.warning(f"خطأ أثناء فك تشفير صورة QR محلياً: {e}")
        return False, None, "تعذر معالجة وقراءة ملف الصورة"


def enroll_recovery_credential(
    user_id: int,
    pin: str,
    actor_context: Optional[dict] = None,
    clear_requirement: bool = True
) -> Tuple[bool, Optional[dict], str]:
    """
    إنشاء وتفعيل اعتماد استرداد جديد لحساب المستخدم.
    - يتطلب رقم PIN من 6 إلى 10 أرقام.
    - يولد سراً عشوائياً بإنتروبيا 256 بت.
    - يلغي أي اعتماد استرداد سابق للمستخدم.
    - يعيد حزمة البطاقة (QR Data URL + رمز الاسترداد اليدوي + المعرف العام).
    """
    clean_pin = pin.strip() if pin else ""
    if not clean_pin or not clean_pin.isdigit() or len(clean_pin) < 6 or len(clean_pin) > 10:
        return False, None, "رقم PIN الخاص بالاسترداد يجب أن يتكون من 6 إلى 10 أرقام"

    raw_secret_bytes = secrets.token_bytes(32)
    raw_secret_hex = raw_secret_bytes.hex()  # 64 hex chars
    formatted_code = format_manual_code(raw_secret_hex)

    year_str = datetime.utcnow().strftime('%Y')
    public_id = f"RC-{year_str}-{secrets.token_hex(6).upper()}"

    secret_verifier = _hash_argon2(raw_secret_hex)
    pin_verifier = _hash_argon2(clean_pin)

    user_info = None
    with get_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            return False, None, "المستخدم غير موجود أو حسابه معطل"

        user_info = {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role
        }

        # إلغاء أي اعتمادات نشطة سابقة للمستخدم
        existing_creds = (
            session.query(AccountRecoveryCredential)
            .filter(AccountRecoveryCredential.user_id == user.id, AccountRecoveryCredential.status == 'active')
            .all()
        )
        for old_cred in existing_creds:
            old_cred.status = 'superseded'
            old_cred.revoked_at = datetime.utcnow()

        # إنشاء وحفظ الاعتماد الجديد
        new_cred = AccountRecoveryCredential(
            user_id=user.id,
            credential_public_id=public_id,
            secret_verifier=secret_verifier,
            pin_verifier=pin_verifier,
            version=QR_PAYLOAD_VERSION,
            status='active',
            created_at=datetime.utcnow(),
            failure_count=0
        )
        session.add(new_cred)
        if clear_requirement:
            user.must_enroll_recovery = 0

    # بناء حمولة رمز QR
    qr_payload = {
        "type": QR_PAYLOAD_TYPE,
        "version": QR_PAYLOAD_VERSION,
        "credential_id": public_id,
        "account_public_id": user_info["username"],
        "secret": raw_secret_hex
    }

    qr_data_url = generate_qr_image_base64(qr_payload)

    # توثيق الحدث في سجل التدقيق خارج معاملة الجلسة
    audit_service.record_event(
        action="auth.recovery.enrolled",
        category="auth",
        user={"id": user_info["id"], "username": user_info["username"], "role": user_info["role"]},
        object_type="recovery_credential",
        object_id=public_id,
        success=True,
        metadata={
            "credential_id": public_id,
            "user_id": user_info["id"],
            "username": user_info["username"],
            "enrolled_by": actor_context.get('username') if actor_context else user_info["username"]
        }
    )

    recovery_card_data = {
        "credential_id": public_id,
        "username": user_info["username"],
        "full_name": user_info["full_name"],
        "manual_recovery_code": formatted_code,
        "qr_image_data_url": qr_data_url,
        "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    }

    return True, recovery_card_data, "تم إنشاء وتفعيل بطاقة استرداد الحساب بنجاح"


def verify_recovery_and_authorize(
    identifier: str,
    secret_or_code: str,
    pin: str,
    client_ip: str = '127.0.0.1',
    credential_id_hint: Optional[str] = None
) -> Tuple[bool, Optional[dict], str, Optional[str]]:
    """
    التحقق الصارم من مدخلات الاسترداد (QR / رمز يدوي + PIN):
    - فحص الكبح والقفل المسبق.
    - مطابقة التجزئة عبر Argon2id.
    - إصدار رمز تفويض مؤقت لمرة واحدة (TTL: 10 دقائق).
    - تعيد: (success, result_dict, user_message, error_code)
    """
    clean_id = (identifier or '').strip()
    clean_secret = normalize_manual_code(secret_or_code)
    clean_pin = (pin or '').strip()

    if not clean_id or not clean_secret or not clean_pin:
        return False, None, "تعذر التحقق من بيانات الاسترداد. يرجى إدخال كافة البيانات المطلوبة.", ErrorCode.VALIDATION_ERROR

    # 1. فحص القفل المؤقت لاسم المستخدم وعنوان IP
    locked, remaining_sec, _ = is_locked_out(clean_id, client_ip)
    if locked:
        audit_service.record_event(
            action="auth.recovery.locked_out",
            category="auth",
            object_type="user",
            success=False,
            failure_reason_code="RECOVERY_LOCKED_OUT",
            metadata={"attempted_username": clean_id, "remaining_seconds": remaining_sec}
        )
        return False, None, f"تم كبح محاولات الاسترداد مؤقتاً لحماية أمان الحساب. يرجى الانتظار {remaining_sec} ثانية.", ErrorCode.RECOVERY_LOCKED_OUT

    user_found = False
    cred_found = False
    cred_locked = False
    remain_m = 0
    secret_ok = False
    pin_ok = False
    cred_public_id = ""
    user_data = None
    raw_reset_token = None

    with get_session() as session:
        user = session.query(User).filter(User.username.ilike(clean_id)).first()
        if user and getattr(user, 'is_active', 1) != 0:
            user_found = True
            user_data = {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role
            }

            cred_query = session.query(AccountRecoveryCredential).filter(
                AccountRecoveryCredential.user_id == user.id,
                AccountRecoveryCredential.status == 'active'
            )
            if credential_id_hint:
                cred_query = cred_query.filter(AccountRecoveryCredential.credential_public_id == credential_id_hint.strip())

            cred = cred_query.first()
            if cred:
                cred_found = True
                cred_public_id = cred.credential_public_id
                if cred.locked_until and cred.locked_until > datetime.utcnow():
                    cred_locked = True
                    remain_m = int((cred.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
                else:
                    secret_ok = _verify_argon2(cred.secret_verifier, clean_secret)
                    pin_ok = _verify_argon2(cred.pin_verifier, clean_pin)

                    if not secret_ok or not pin_ok:
                        cred.failure_count = (cred.failure_count or 0) + 1
                        if cred.failure_count >= 5:
                            cred.locked_until = datetime.utcnow() + timedelta(minutes=15)
                    else:
                        # نجاح التحقق
                        cred.failure_count = 0
                        cred.locked_until = None

                        raw_reset_token = f"rst_{secrets.token_urlsafe(32)}"
                        token_hash = hashlib.sha256(raw_reset_token.encode('utf-8')).hexdigest()

                        session.query(RecoveryTransaction).filter(
                            RecoveryTransaction.user_id == user.id,
                            RecoveryTransaction.state == 'pending'
                        ).update({"state": "revoked"})

                        tx = RecoveryTransaction(
                            user_id=user.id,
                            credential_id=cred.id,
                            token_hash=token_hash,
                            state='pending',
                            expires_at=datetime.utcnow() + timedelta(minutes=10),
                            client_ip=client_ip,
                            request_id=secrets.token_hex(8)
                        )
                        session.add(tx)

    # معالجة النتائج خارج الجلسة لتجنب القفل التبادلي
    if not user_found:
        record_failed_attempt(clean_id, client_ip)
        audit_service.record_event(
            action="auth.recovery.failed",
            category="auth",
            object_type="user",
            success=False,
            failure_reason_code="USER_NOT_FOUND",
            metadata={"attempted_username": clean_id}
        )
        return False, None, "تعذر التحقق من بيانات الاسترداد. يرجى التأكد من اسم المستخدم ورمز الاسترداد ورقم PIN.", ErrorCode.RECOVERY_INVALID_CREDENTIAL

    if not cred_found:
        record_failed_attempt(clean_id, client_ip)
        audit_service.record_event(
            action="auth.recovery.failed",
            category="auth",
            user={"id": user_data["id"], "username": user_data["username"]},
            object_type="recovery_credential",
            success=False,
            failure_reason_code="NO_ACTIVE_CREDENTIAL",
            metadata={"username": user_data["username"]}
        )
        return False, None, "تعذر التحقق من بيانات الاسترداد. الحساب لا يحتوي على بطاقة استرداد مفعلة.", ErrorCode.RECOVERY_NOT_CONFIGURED

    if cred_locked:
        return False, None, f"تم قفل بطاقة الاسترداد مؤقتاً لتكرار المحاولات الخاطئة. يرجى المحاولة بعد {remain_m} دقيقة.", ErrorCode.RECOVERY_LOCKED_OUT

    if not secret_ok or not pin_ok:
        record_failed_attempt(clean_id, client_ip)
        audit_service.record_event(
            action="auth.recovery.failed",
            category="auth",
            user={"id": user_data["id"], "username": user_data["username"]},
            object_type="recovery_credential",
            object_id=cred_public_id,
            success=False,
            failure_reason_code="INVALID_SECRET_OR_PIN",
            metadata={
                "credential_id": cred_public_id,
                "secret_matched": secret_ok,
                "pin_matched": pin_ok
            }
        )
        return False, None, "تعذر التحقق من بيانات الاسترداد. يرجى التأكد من الرمز ورقم PIN.", ErrorCode.RECOVERY_INVALID_CREDENTIAL

    # نجاح كامل
    record_successful_login(clean_id, client_ip)
    audit_service.record_event(
        action="auth.recovery.succeeded",
        category="auth",
        user={"id": user_data["id"], "username": user_data["username"], "role": user_data["role"]},
        object_type="recovery_transaction",
        object_id=cred_public_id,
        success=True,
        metadata={
            "credential_id": cred_public_id,
            "username": user_data["username"],
            "ttl_minutes": 10
        }
    )

    return True, {
        "reset_token": raw_reset_token,
        "username": user_data["username"],
        "full_name": user_data["full_name"],
        "expires_in_seconds": 600
    }, "تم التحقق من بيانات الاسترداد بنجاح! يرجى إدخال كلمة المرور الجديدة.", None


def complete_password_reset_with_token(
    reset_token: str,
    new_password: str,
    confirm_password: str,
    client_ip: str = '127.0.0.1'
) -> Tuple[bool, str, Optional[str]]:
    """
    إتمام إعادة تعيين كلمة المرور باستخدام رمز التفويض المؤقت:
    - التحقق من مطابقة ومتانة كلمة المرور.
    - ترقية إصدار الجلسة session_version لإبطال الجلسات السابقة فوراً.
    - إغلاق معاملة الاسترداد ومنع إعادة استخدام الرمز.
    - تصفير قيود الكبح والحظر على الحساب.
    """
    if not reset_token:
        return False, "رمز تفويض الاسترداد مفقود", ErrorCode.VALIDATION_ERROR

    if not new_password or not confirm_password:
        return False, "يرجى إدخال كلمة المرور الجديدة وتأكيدها", ErrorCode.VALIDATION_ERROR

    if new_password != confirm_password:
        return False, "كلمة المرور وتأكيدها غير متطابقين", ErrorCode.VALIDATION_ERROR

    token_hash = hashlib.sha256(reset_token.strip().encode('utf-8')).hexdigest()

    user_event_data = None
    with get_session() as session:
        tx = (
            session.query(RecoveryTransaction)
            .filter(RecoveryTransaction.token_hash == token_hash)
            .first()
        )

        if not tx or tx.state != 'pending':
            return False, "رمز تفويض الاسترداد غير صالح أو تم استخدامه مسبقاً", ErrorCode.RECOVERY_TOKEN_EXPIRED

        if tx.expires_at < datetime.utcnow():
            tx.state = 'expired'
            return False, "انتهت صلاحية جلسة الاسترداد (المهلة 10 دقائق). يرجى إعادة المحاولة.", ErrorCode.RECOVERY_TOKEN_EXPIRED

        user = session.query(User).filter(User.id == tx.user_id).first()
        if not user or getattr(user, 'is_active', 1) == 0:
            tx.state = 'revoked'
            return False, "المستخدم المرتبط بهذه المعاملة غير صالح أو معطل", ErrorCode.ACCOUNT_DISABLED

        # التحقق من متانة كلمة المرور وفق السياسة المعتمدة
        is_valid, err_msg = validate_password_strength(new_password, username=user.username, full_name=user.full_name)
        if not is_valid:
            return False, err_msg, ErrorCode.PASSWORD_TOO_WEAK

        # تحديث كلمة المرور وإبطال الجلسات السابقة
        user.password_hash = hash_password(new_password)
        user.session_version = getattr(user, 'session_version', 1) + 1

        # تحديث حالة المعاملة والاعتماد
        tx.state = 'completed'
        tx.used_at = datetime.utcnow()

        cred = session.query(AccountRecoveryCredential).filter(AccountRecoveryCredential.id == tx.credential_id).first()
        if cred:
            cred.last_used_at = datetime.utcnow()
            cred.failure_count = 0
            cred.locked_until = None

        # تصفير أي قفل مسجل على الحساب
        user_ident = f"user_{user.username.lower()}"
        lockouts = session.query(AuthLockout).filter(AuthLockout.identifier.in_([user_ident, user.username.lower()])).all()
        for lo in lockouts:
            lo.failed_count = 0
            lo.locked_until = None
            lo.lockout_count = 0

        user_event_data = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "session_version": user.session_version
        }

    # توثيق الحدث خارج الجلسة
    audit_service.record_event(
        action="auth.recovery.password_reset",
        category="auth",
        user={"id": user_event_data["id"], "username": user_event_data["username"], "role": user_event_data["role"]},
        object_type="user",
        object_id=str(user_event_data["id"]),
        success=True,
        metadata={
            "username": user_event_data["username"],
            "user_id": user_event_data["id"],
            "session_version": user_event_data["session_version"],
            "method": "offline_qr_recovery"
        }
    )

    return True, "تم تغيير كلمة المرور بنجاح! يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.", None


def revoke_recovery_credential(user_id: int, actor_user: Optional[dict] = None) -> Tuple[bool, str]:
    """إلغاء بطاقة الاسترداد لحساب المستخدم بواسطة المدير أو المستخدم نفسه."""
    username = ""
    with get_session() as session:
        creds = (
            session.query(AccountRecoveryCredential)
            .filter(AccountRecoveryCredential.user_id == user_id, AccountRecoveryCredential.status == 'active')
            .all()
        )
        if not creds:
            return False, "لا توجد بطاقة استرداد نشطة لهذا الحساب"

        for c in creds:
            c.status = 'revoked'
            c.revoked_at = datetime.utcnow()

        user = session.query(User).filter(User.id == user_id).first()
        username = user.username if user else str(user_id)

    # توثيق الحدث خارج الجلسة
    audit_service.record_event(
        action="auth.recovery.revoked",
        category="auth",
        user=actor_user,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={
            "user_id": user_id,
            "username": username,
            "revoked_by": actor_user.get('username') if actor_user else 'system'
        }
    )
    return True, f"تم إلغاء بطاقة استرداد الحساب للمستخدم {username} بنجاح"


def get_user_recovery_status(user_id: int) -> dict:
    """استرجاع الحالة العامة الآمنة لبطاقة استرداد الحساب دون كشف أي أسرار."""
    with get_session() as session:
        cred = (
            session.query(AccountRecoveryCredential)
            .filter(AccountRecoveryCredential.user_id == user_id)
            .order_by(AccountRecoveryCredential.id.desc())
            .first()
        )
        if not cred:
            return {
                "configured": False,
                "status": "not_configured",
                "status_label_ar": "غير مفعل",
                "created_at": "",
                "credential_id": ""
            }

        is_active = (cred.status == 'active')
        return {
            "configured": is_active,
            "status": cred.status,
            "status_label_ar": "مفعل" if is_active else ("ملغي" if cred.status == 'revoked' else "مستبدل"),
            "created_at": cred.created_at.strftime('%Y-%m-%d %H:%M') if cred.created_at else "",
            "last_used_at": cred.last_used_at.strftime('%Y-%m-%d %H:%M') if cred.last_used_at else "",
            "credential_id": cred.credential_public_id if is_active else ""
        }
