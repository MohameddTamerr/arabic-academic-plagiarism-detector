# -*- coding: utf-8 -*-
"""
مسارات واجهة برمجة تطبيقات استرداد الحسابات (Account Recovery API Routes):
- فك تشفير رموز QR المرفوعة أو الملتقطة عبر الكاميرا محلياً (100% Offline).
- التحقق من اعتمادات الاسترداد وإصدار رموز التفويض المؤقتة.
- إتمام إعادة تعيين كلمة المرور وتدوير الجلسات.
- تفعيل وإعادة توليد بطاقات الاسترداد للمستخدمين والمديرين.
"""

import base64
from flask import Blueprint, request, jsonify, session as flask_session, g
from app.services import recovery_service
from app.security.authorization import get_authenticated_user, require_permission, has_permission
from app.security.permissions import Permission
from app.repositories import user_repo
from app.errors.error_codes import ErrorCode

recovery_bp = Blueprint('recovery_bp', __name__)


@recovery_bp.route('/api/recovery/decode_qr', methods=['POST'])
def decode_qr_route():
    """
    فك تشفير رمز QR من الصورة المرفوعة أو إطار الكاميرا محلياً دون أي اتصال خارجي.
    - يدعم ملفات multipart/form-data أو JSON المحتوي على Base64 data URI.
    """
    image_bytes = None

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            image_bytes = file.read()
    elif request.is_json:
        data = request.get_json(silent=True) or {}
        img_data = data.get('image_data') or data.get('frame_data') or ''
        if img_data:
            if ',' in img_data:
                img_data = img_data.split(',', 1)[1]
            try:
                image_bytes = base64.b64decode(img_data)
            except Exception:
                return jsonify({'success': False, 'error': 'بيانات الصورة المشفرة غير صالحة', 'error_code': ErrorCode.VALIDATION_ERROR}), 400

    if not image_bytes:
        return jsonify({'success': False, 'error': 'لم يتم استلام أي ملف صورة صالح', 'error_code': ErrorCode.VALIDATION_ERROR}), 400

    ok, payload, msg = recovery_service.decode_qr_from_bytes(image_bytes)
    if not ok or not payload:
        return jsonify({'success': False, 'error': msg, 'error_code': ErrorCode.FILE_UNREADABLE}), 400

    # التحقق من نوع وهيكل حمولة QR
    if payload.get('type') != recovery_service.QR_PAYLOAD_TYPE:
        return jsonify({'success': False, 'error': 'رمز QR هذا ليس بطاقة استرداد معتمدة للمنظومة', 'error_code': ErrorCode.RECOVERY_INVALID_CREDENTIAL}), 400

    return jsonify({
        'success': True,
        'payload': payload,
        'message': msg
    })


@recovery_bp.route('/api/recovery/verify_and_authorize', methods=['POST'])
def verify_and_authorize_route():
    """
    التحقق من بيانات اعتماد الاسترداد (QR / رمز يدوي + PIN) وإصدار رمز تفويض مؤقت.
    """
    data = request.get_json(silent=True) or request.form or {}
    username = (data.get('username') or '').strip()
    secret_or_code = (data.get('secret') or data.get('code') or data.get('manual_code') or '').strip()
    pin = (data.get('pin') or '').strip()
    cred_hint = (data.get('credential_id') or '').strip() or None
    client_ip = request.remote_addr or '127.0.0.1'

    # إذا تم إرسال كائن qr_payload مباشرة
    qr_payload = data.get('qr_payload')
    if isinstance(qr_payload, dict):
        if not username:
            username = (qr_payload.get('account_public_id') or '').strip()
        if not secret_or_code:
            secret_or_code = (qr_payload.get('secret') or '').strip()
        if not cred_hint:
            cred_hint = (qr_payload.get('credential_id') or '').strip() or None

    ok, result, msg, err_code = recovery_service.verify_recovery_and_authorize(
        identifier=username,
        secret_or_code=secret_or_code,
        pin=pin,
        client_ip=client_ip,
        credential_id_hint=cred_hint
    )

    if not ok:
        status_code = 429 if err_code == ErrorCode.RECOVERY_LOCKED_OUT else 400
        return jsonify({
            'success': False,
            'error': msg,
            'error_code': err_code or ErrorCode.RECOVERY_INVALID_CREDENTIAL
        }), status_code

    return jsonify({
        'success': True,
        'reset_token': result.get('reset_token'),
        'username': result.get('username'),
        'full_name': result.get('full_name'),
        'expires_in_seconds': result.get('expires_in_seconds', 600),
        'message': msg
    })


@recovery_bp.route('/api/recovery/complete_reset', methods=['POST'])
def complete_reset_route():
    """
    إتمام تغيير كلمة المرور للمستخدم المصرح له عبر رمز الاسترداد المؤقت.
    """
    data = request.get_json(silent=True) or request.form or {}
    reset_token = (data.get('reset_token') or '').strip()
    new_pass = (data.get('new_password') or '').strip()
    confirm_pass = (data.get('confirm_password') or '').strip()
    client_ip = request.remote_addr or '127.0.0.1'

    ok, msg, err_code = recovery_service.complete_password_reset_with_token(
        reset_token=reset_token,
        new_password=new_pass,
        confirm_password=confirm_pass,
        client_ip=client_ip
    )

    if not ok:
        return jsonify({
            'success': False,
            'error': msg,
            'error_code': err_code or ErrorCode.VALIDATION_ERROR
        }), 400

    return jsonify({
        'success': True,
        'message': msg
    })


@recovery_bp.route('/api/recovery/enroll', methods=['POST'])
def enroll_recovery_route():
    """
    إنشاء وتفعيل بطاقة استرداد الحساب للمستخدم المسجل دخوله حالياً.
    """
    user = get_authenticated_user()
    if not user:
        return jsonify({'success': False, 'error': 'يجب تسجيل الدخول أولاً', 'error_code': ErrorCode.AUTH_REQUIRED}), 401

    data = request.get_json(silent=True) or request.form or {}
    pin = (data.get('pin') or '').strip()

    ok, card_data, msg = recovery_service.enroll_recovery_credential(
        user_id=user.get('id'),
        pin=pin,
        actor_context=user
    )

    if not ok:
        return jsonify({'success': False, 'error': msg, 'error_code': ErrorCode.VALIDATION_ERROR}), 400

    return jsonify({
        'success': True,
        'recovery_card': card_data,
        'message': msg
    })


@recovery_bp.route('/api/recovery/regenerate', methods=['POST'])
def regenerate_recovery_route():
    """
    إعادة توليد بطاقة الاسترداد للمستخدم الحالي بعد تأكيد كلمة المرور وتعيين PIN جديد.
    """
    user = get_authenticated_user()
    if not user:
        return jsonify({'success': False, 'error': 'يجب تسجيل الدخول أولاً', 'error_code': ErrorCode.AUTH_REQUIRED}), 401

    data = request.get_json(silent=True) or request.form or {}
    current_pass = (data.get('current_password') or '').strip()
    new_pin = (data.get('new_pin') or '').strip()

    # التحقق من كلمة المرور الحالية
    auth_user = user_repo.authenticate_user(user.get('username'), current_pass)
    if not auth_user:
        return jsonify({'success': False, 'error': 'كلمة المرور الحالية غير صحيحة', 'error_code': ErrorCode.AUTH_INVALID_CREDENTIAL}), 400

    ok, card_data, msg = recovery_service.enroll_recovery_credential(
        user_id=user.get('id'),
        pin=new_pin,
        actor_context=user
    )

    if not ok:
        return jsonify({'success': False, 'error': msg, 'error_code': ErrorCode.VALIDATION_ERROR}), 400

    return jsonify({
        'success': True,
        'recovery_card': card_data,
        'message': 'تمت إعادة توليد بطاقة استرداد الحساب وإلغاء الرمز السابق بنجاح'
    })


@recovery_bp.route('/api/recovery/status', methods=['GET'])
def get_recovery_status_route():
    """استرجاع حالة إعداد استرداد الحساب للمستخدم الحالي."""
    user = get_authenticated_user()
    if not user:
        return jsonify({'success': False, 'error': 'يجب تسجيل الدخول أولاً', 'error_code': ErrorCode.AUTH_REQUIRED}), 401

    status_data = recovery_service.get_user_recovery_status(user.get('id'))
    return jsonify({
        'success': True,
        'recovery_status': status_data
    })


@recovery_bp.route('/api/admin/users/<int:user_id>/recovery_status', methods=['GET'])
@require_permission(Permission.USERS_VIEW)
def admin_get_user_recovery_status(user_id: int):
    """استعراض حالة استرداد حساب مستخدم بواسطة المدير."""
    status_data = recovery_service.get_user_recovery_status(user_id)
    return jsonify({
        'success': True,
        'user_id': user_id,
        'recovery_status': status_data
    })


@recovery_bp.route('/api/admin/users/<int:user_id>/revoke_recovery', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def admin_revoke_user_recovery(user_id: int):
    """إلغاء بطاقة استرداد حساب موظف بواسطة مدير النظام."""
    user = get_authenticated_user()
    ok, msg = recovery_service.revoke_recovery_credential(user_id, actor_user=user)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400
    return jsonify({'success': True, 'message': msg})


@recovery_bp.route('/api/admin/users/<int:user_id>/enroll_recovery', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def admin_enroll_user_recovery(user_id: int):
    """توليد بطاقة استرداد لموظف بواسطة مدير النظام أثناء الإعداد المساعد."""
    user = get_authenticated_user()
    data = request.get_json(silent=True) or request.form or {}
    pin = (data.get('pin') or '').strip()

    ok, card_data, msg = recovery_service.enroll_recovery_credential(
        user_id=user_id,
        pin=pin,
        actor_context=user
    )
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400

    return jsonify({
        'success': True,
        'recovery_card': card_data,
        'message': msg
    })
