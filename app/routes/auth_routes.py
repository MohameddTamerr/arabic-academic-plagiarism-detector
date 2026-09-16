import time
from flask import Blueprint, request, jsonify, session as flask_session, g
from app.repositories import user_repo
from app.services import audit_service
from app.services.login_throttling_service import is_locked_out, record_failed_attempt, record_successful_login
from app.security.csrf import generate_csrf_token, rotate_csrf_token
from app.security.permissions import Permission, Role, ROLE_LABELS_AR, get_user_permissions
from app.security.authorization import require_permission, get_authenticated_user, has_permission
from app.errors.error_codes import ErrorCode

auth_bp = Blueprint('auth_bp', __name__)


def is_localhost_request(req=None) -> bool:
    """
    التحقق الصارم من أن الطلب وارد من الجهاز المحلي فقط (Direct Socket Peer).
    يتجاهل أي ترويسات وكيل غير موثوقة (X-Forwarded-For, X-Real-IP, Forwarded) لمنع الانتحال.
    """
    if req is None:
        req = request

    # قراءة عنوان الاتصال المباشر من بيئة WSGI (Socket Peer IP)
    remote_ip = req.environ.get('REMOTE_ADDR') or req.remote_addr or ''
    remote_ip = remote_ip.strip()

    # العناوين المحلية المسموح بها فقط
    if remote_ip in ('127.0.0.1', '::1', 'localhost', '::ffff:127.0.0.1'):
        return True
    if remote_ip.startswith('127.'):
        return True
    return False


@auth_bp.route('/api/auth/status', methods=['GET'])
@auth_bp.route('/api/auth/setup_status', methods=['GET'])
def get_auth_status():
    """التحقق من حالة النظام وهل يحتاج لإعداد المدير الأول مع تقييد الوصول للشبكة المحلية."""
    setup_required = user_repo.is_initial_admin_allowed()
    is_local = is_localhost_request()
    return jsonify({
        'needs_first_time_setup': setup_required and is_local,
        'setup_required': setup_required,
        'setup_pending': setup_required and not is_local,
        'is_localhost': is_local,
        'bootstrap_allowed': setup_required and is_local,
        'pending_message': 'لم يتم الانتهاء من إعداد النظام على جهاز الخادم بعد. يرجى التواصل مع مسؤول النظام.' if (setup_required and not is_local) else None
    })


@auth_bp.route('/api/auth/csrf-token', methods=['GET'])
@auth_bp.route('/api/auth/csrf_token', methods=['GET'])
def get_csrf_token_route():
    """استرجاع أو توليد رمز CSRF الآمن المرتبط بالجلسة الحالية."""
    token = generate_csrf_token()
    return jsonify({'csrf_token': token})


@auth_bp.route('/api/auth/me', methods=['GET'])
def get_current_user_profile():
    """استرجاع بيانات المستخدم الحالي وصلاحياته المعتمدة ورمز CSRF."""
    user = get_authenticated_user()
    if not user:
        return jsonify({'authenticated': False, 'user': None}), 200
    user_data = dict(user)
    user_data['permissions'] = get_user_permissions(user)
    user_data['role_label_ar'] = ROLE_LABELS_AR.get(user.get('role'), user.get('role'))
    csrf_token = generate_csrf_token()
    return jsonify({'authenticated': True, 'user': user_data, 'csrf_token': csrf_token})


@auth_bp.route('/api/auth/setup_first_admin', methods=['POST'])
@auth_bp.route('/api/auth/setup_admin', methods=['POST'])
def setup_first_admin():
    """إنشاء حساب مدير النظام الأول في مرحلة الإعداد الأولى فقط من الخادم المحلي حصرياً."""
    # 1. التحقق الصارم من أن الطلب محلي حصراً (Localhost-Only Enforcement)
    if not is_localhost_request():
        audit_service.record_event(
            action="auth.setup_admin.rejected_remote",
            category="security",
            success=False,
            failure_reason_code="REMOTE_BOOTSTRAP_FORBIDDEN",
            metadata={"remote_addr": request.remote_addr, "client_ip": request.remote_addr}
        )
        return jsonify({
            'success': False,
            'error_code': ErrorCode.FORBIDDEN_ORIGIN,
            'status': 'SYSTEM_SETUP_PENDING',
            'error': 'لم يتم الانتهاء من إعداد النظام على جهاز الخادم بعد. يرجى التواصل مع مسؤول النظام.'
        }), 403

    # 2. التحقق من صلاحية التهيئة الأولية
    if not user_repo.is_initial_admin_allowed():
        return jsonify({
            'success': False,
            'error_code': ErrorCode.FIRST_ADMIN_ALREADY_EXISTS,
            'error': 'تم إعداد مدير النظام مسبقاً.'
        }), 400

    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    pin = (data.get('recovery_pin') or data.get('pin') or '').strip()

    if not username or not password or not full_name:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.VALIDATION_ERROR,
            'error': 'يرجى إدخال كافة البيانات المطلوبة لمدير النظام.'
        }), 400

    # 3. اشتراط رمز PIN للاسترداد الفوري
    if not pin or not (pin.isdigit() and 6 <= len(pin) <= 10):
        return jsonify({
            'success': False,
            'error_code': ErrorCode.VALIDATION_ERROR,
            'error': 'رمز PIN الخاص ببطاقة الاسترداد مطلوب ويجب أن يتكون من 6 إلى 10 أرقام.'
        }), 400

    ok, msg = user_repo.create_initial_admin(username, password, full_name)
    if ok:
        user, _ = user_repo.authenticate_or_reset_user(username, password)
        recovery_card = None
        if user:
            from app.services import recovery_service
            rec_ok, card_data, rec_err = recovery_service.enroll_recovery_credential(user.get('id'), pin, actor_context=user)
            if rec_ok:
                recovery_card = card_data

        audit_service.record_event(
            action="auth.setup_admin",
            category="auth",
            user=user,
            object_type="user",
            object_id=str(user.get('id', '')) if user else '',
            success=True,
            metadata={"username": username, "full_name": full_name, "role": "system_admin"}
        )
        return jsonify({
            'success': True,
            'message': msg,
            'user': user,
            'recovery_card': recovery_card
        })

    audit_service.record_event(
        action="auth.setup_admin.failed",
        category="auth",
        success=False,
        failure_reason_code="SETUP_FAILED",
        metadata={"username": username}
    )
    return jsonify({'success': False, 'error_code': ErrorCode.FIRST_ADMIN_ALREADY_EXISTS, 'error': msg}), 400


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """تسجيل الدخول مع الحماية ضد القوة الغاشمة وتدوير الجلسة وتوثيق التدقيق."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    client_ip = request.remote_addr or '127.0.0.1'

    # 1. فحص القفل المؤقت المسبق
    locked, remaining_sec, _ = is_locked_out(username, client_ip)
    if locked:
        audit_service.record_event(
            action="auth.login.locked_out",
            category="auth",
            object_type="user",
            success=False,
            failure_reason_code="ACCOUNT_LOCKED_OUT",
            metadata={'attempted_username': username, 'remaining_seconds': remaining_sec}
        )
        return jsonify({
            'success': False,
            'error_code': ErrorCode.AUTH_LOCKED_OUT,
            'error': 'تم كبح محاولات تسجيل الدخول مؤقتاً لحماية أمان النظام. يرجى المحاولة لاحقاً.',
            'retry_after_seconds': remaining_sec
        }), 429

    user, was_reset = user_repo.authenticate_or_reset_user(username, password)
    if user:
        # تصفير عداد الإخفاق
        record_successful_login(username, client_ip)

        # منع تثبيت الجلسة (Session Fixation Defense): تفريغ الجلسة وتوليد معرفات ورموز جديدة
        flask_session.clear()
        flask_session['user_id'] = user.get('id')
        flask_session['username'] = user.get('username')
        flask_session['role'] = user.get('role')
        flask_session['session_version'] = user.get('session_version', 1)
        flask_session['auth_time'] = time.time()
        flask_session['last_activity'] = time.time()
        csrf_token = rotate_csrf_token()

        user_with_perms = dict(user)
        user_with_perms['permissions'] = get_user_permissions(user)
        user_with_perms['role_label_ar'] = ROLE_LABELS_AR.get(user.get('role'), user.get('role'))

        audit_service.record_event(
            action="auth.login.success",
            category="auth",
            user=user,
            object_type="user",
            object_id=str(user.get('id', '')),
            success=True,
            metadata={'username': user.get('username'), 'role': user.get('role'), 'was_reset': was_reset}
        )
        return jsonify({
            'success': True,
            'user': user_with_perms,
            'csrf_token': csrf_token,
            'password_was_reset': was_reset,
            'message': 'تم اعتماد كلمة المرور الجديدة بنجاح وتسجيل دخولك إلى المنظومة!' if was_reset else 'مرحباً بك في المنظومة الأكاديمية'
        })

    # تسجيل محاولة الإخفاق وتطبيق القفل إذا بلغت العتبة
    now_locked, total_failed, locked_until = record_failed_attempt(username, client_ip)
    if now_locked:
        audit_service.record_event(
            action="auth.lockout.triggered",
            category="auth",
            object_type="user",
            success=False,
            failure_reason_code="MAX_ATTEMPTS_EXCEEDED",
            metadata={'attempted_username': username, 'failed_count': total_failed}
        )
        remaining_sec = getattr(config, 'AUTH_LOCKOUT_DURATION_MINUTES', 15) * 60
        return jsonify({
            'success': False,
            'error_code': ErrorCode.AUTH_LOCKED_OUT,
            'error': 'تم كبح محاولات تسجيل الدخول مؤقتاً لحماية أمان النظام. يرجى المحاولة لاحقاً.',
            'retry_after_seconds': remaining_sec
        }), 429

    audit_service.record_event(
        action="auth.login.failure",
        category="auth",
        object_type="user",
        success=False,
        failure_reason_code="INVALID_CREDENTIALS",
        metadata={'attempted_username': username, 'failed_count': total_failed}
    )
    return jsonify({
        'success': False,
        'error_code': ErrorCode.AUTH_INVALID_CREDENTIALS,
        'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'
    }), 401


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout_route():
    """تسجيل الخروج الآمن وتفريغ الجلسة وتدوير المعرفات وتوثيق الحدث."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip() or flask_session.get('username', '')
    flask_session.clear()
    rotate_csrf_token()
    audit_service.record_event(
        action="auth.logout",
        category="auth",
        user={"username": username} if username else None,
        success=True
    )
    return jsonify({'success': True, 'message': 'تم تسجيل الخروج بنجاح'})


@auth_bp.route('/api/auth/change_password', methods=['POST'])
def change_password_route():
    """تغيير كلمة المرور من قبل المستخدم مع التحقق من المتانة وإبطال الجلسات الأخرى."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    old_pass = data.get('old_password', '').strip()
    new_pass = data.get('new_password', '').strip()

    ok, msg = user_repo.change_password(username, old_pass, new_pass)
    if ok:
        rotate_csrf_token()
        audit_service.record_event(
            action="auth.password.changed",
            category="auth",
            user={"username": username},
            object_type="user",
            object_id=username,
            success=True
        )
        return jsonify({'success': True, 'message': msg})

    audit_service.record_event(
        action="auth.password.change_failed",
        category="auth",
        user={"username": username},
        object_type="user",
        object_id=username,
        success=False,
        failure_reason_code="INVALID_CURRENT_PASSWORD"
    )
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/complete_first_login', methods=['POST'])
def complete_first_login_route():
    """إتمام إعداد الموظف الإلزامي: كلمة مرور دائمة ثم بطاقة QR للاسترداد."""
    user = get_authenticated_user()
    if not user:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.AUTH_REQUIRED,
            'error': 'انتهت جلسة أول دخول. يرجى تسجيل الدخول بكلمة المرور المؤقتة مرة أخرى.'
        }), 401

    data = request.get_json(silent=True) or request.form or {}
    new_pass = (data.get('new_password') or '').strip()
    confirm_pass = (data.get('confirm_password') or '').strip()
    pin = (data.get('recovery_pin') or data.get('pin') or '').strip()

    must_change = bool(user.get('must_change_password'))
    must_enroll = bool(user.get('must_enroll_recovery'))
    if not must_change and not must_enroll:
        return jsonify({'success': False, 'error': 'تم إكمال إعداد هذا الحساب مسبقاً.'}), 409

    if not pin or not pin.isdigit() or not 6 <= len(pin) <= 10:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.VALIDATION_ERROR,
            'error': 'رمز PIN مطلوب ويجب أن يتكون من 6 إلى 10 أرقام.'
        }), 400

    if must_change:
        if not new_pass or not confirm_pass:
            return jsonify({
                'success': False,
                'error_code': ErrorCode.VALIDATION_ERROR,
                'error': 'كلمة المرور الدائمة وتأكيدها مطلوبان.'
            }), 400
        ok, msg, new_session_version = user_repo.complete_first_login_password(
            user.get('id'), new_pass, confirm_pass
        )
        if not ok:
            return jsonify({'success': False, 'error_code': ErrorCode.VALIDATION_ERROR, 'error': msg}), 400
        flask_session['session_version'] = new_session_version

    from app.services import recovery_service
    rec_ok, card_data, rec_msg = recovery_service.enroll_recovery_credential(
        user_id=user.get('id'),
        pin=pin,
        actor_context=user,
        clear_requirement=False
    )
    if not rec_ok:
        return jsonify({'success': False, 'error_code': ErrorCode.VALIDATION_ERROR, 'error': rec_msg}), 400

    updated_user = user_repo.get_user_by_id(user.get('id')) or dict(user)
    updated_user['permissions'] = get_user_permissions(updated_user)
    updated_user['role_label_ar'] = ROLE_LABELS_AR.get(updated_user.get('role'), updated_user.get('role'))

    audit_service.record_event(
        action='auth.first_login.completed',
        category='auth',
        user=updated_user,
        object_type='user',
        object_id=str(user.get('id')),
        success=True,
        metadata={'username': updated_user.get('username'), 'recovery_enrolled': True}
    )
    return jsonify({
        'success': True,
        'message': 'تم اعتماد كلمة المرور وإعداد بطاقة الاسترداد بنجاح.',
        'user': updated_user,
        'recovery_card': card_data
    })


@auth_bp.route('/api/auth/acknowledge_recovery_card', methods=['POST'])
def acknowledge_recovery_card_route():
    """تأكيد المستخدم أنه حفظ بطاقة QR ثم تحرير الجلسة للاستخدام الطبيعي."""
    user = get_authenticated_user()
    if not user:
        return jsonify({'success': False, 'error': 'يجب تسجيل الدخول أولاً'}), 401
    if user.get('must_change_password'):
        return jsonify({'success': False, 'error': 'يجب اعتماد كلمة المرور الدائمة أولاً'}), 428

    ok, msg = user_repo.mark_recovery_enrollment_complete(user.get('id'))
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400

    updated_user = user_repo.get_user_by_id(user.get('id')) or dict(user)
    updated_user['permissions'] = get_user_permissions(updated_user)
    updated_user['role_label_ar'] = ROLE_LABELS_AR.get(updated_user.get('role'), updated_user.get('role'))
    return jsonify({'success': True, 'message': msg, 'user': updated_user})


@auth_bp.route('/users', methods=['GET', 'POST'])
def handle_users():
    """إدارة المستخدمين (عرض وإضافة)."""
    if request.method == 'GET':
        user = get_authenticated_user()
        if not user or not has_permission(user, Permission.USERS_VIEW):
            from app.security.authorization import record_access_denied_audit
            record_access_denied_audit(user, Permission.USERS_VIEW, "استعراض قائمة المستخدمين")
            return jsonify({'success': False, 'error': 'غير مصرح: ليس لديك صلاحية استعراض المستخدمين.'}), 403
        return jsonify({'users': user_repo.get_users_list()})

    # POST: إضافة مستخدم
    user = get_authenticated_user()
    if not user or not has_permission(user, Permission.USERS_MANAGE):
        from app.security.authorization import record_access_denied_audit
        record_access_denied_audit(user, Permission.USERS_MANAGE, "إضافة مستخدم جديد")
        return jsonify({'success': False, 'error': 'غير مصرح: ليس لديك صلاحية إدارة المستخدمين.'}), 403

    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    role = data.get('role', 'reviewer').strip()

    ok, msg = user_repo.add_user(username, password, full_name, role, enforce_policy=True)
    if ok:
        audit_service.record_event(
            action="user.created",
            category="admin",
            object_type="user",
            object_id=username,
            success=True,
            metadata={"username": username, "full_name": full_name, "role": role}
        )
        return jsonify({'success': True, 'message': msg})

    audit_service.record_event(
        action="user.create_failed",
        category="admin",
        object_type="user",
        object_id=username,
        success=False,
        failure_reason_code="USER_EXISTS_OR_INVALID",
        metadata={"username": username, "role": role}
    )
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/users/<int:user_id>/role', methods=['PUT', 'POST'])
@require_permission(Permission.USERS_MANAGE)
def update_user_role_route(user_id):
    """تحديث دور مستخدم وتوثيق الحدث في سجل التدقيق."""
    data = request.get_json(silent=True) or request.form or {}
    new_role = data.get('role', '').strip()
    if not new_role:
        return jsonify({'success': False, 'error': 'يرجى تحديد الدور الجديد'}), 400

    ok, msg, prev_role = user_repo.update_user_role(user_id, new_role)
    if ok:
        audit_service.record_event(
            action="user.role_changed",
            category="admin",
            object_type="user",
            object_id=str(user_id),
            success=True,
            metadata={"user_id": user_id, "previous_role": prev_role, "new_role": new_role}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@require_permission(Permission.USERS_MANAGE)
def delete_user_route(user_id):
    """حذف حساب مستخدم بواسطة المدير."""
    ok, msg = user_repo.delete_user(user_id)
    if ok:
        audit_service.record_event(
            action="user.deleted",
            category="admin",
            object_type="user",
            object_id=str(user_id),
            success=True,
            metadata={"user_id": user_id}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/forgot_password/request', methods=['POST'])
def forgot_password_request_route():
    """تقديم طلب استعادة كلمة مرور من الموظف لمدير النظام."""
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username', '').strip()
    new_password = data.get('new_password', '').strip()

    ok, msg = user_repo.request_password_reset(username, new_password)
    if ok:
        audit_service.record_event(
            action="user.password_reset_requested",
            category="auth",
            object_type="user",
            object_id=username,
            success=True,
            metadata={"username": username}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/password_resets', methods=['GET'])
@require_permission(Permission.USERS_MANAGE)
def get_password_resets_route():
    return jsonify({'requests': user_repo.get_password_reset_requests()})


@auth_bp.route('/api/admin/password_resets/<int:req_id>/approve', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def approve_password_reset_route(req_id):
    ok, msg = user_repo.approve_password_reset(req_id)
    if ok:
        audit_service.record_event(
            action="user.password_reset_approved",
            category="admin",
            object_type="password_reset_request",
            object_id=str(req_id),
            success=True,
            metadata={"request_id": req_id}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/password_resets/<int:req_id>/decline', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def decline_password_reset_route(req_id):
    ok, msg = user_repo.decline_password_reset(req_id)
    if ok:
        audit_service.record_event(
            action="user.password_reset_declined",
            category="admin",
            object_type="password_reset_request",
            object_id=str(req_id),
            success=True,
            metadata={"request_id": req_id}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/admin/users/<int:user_id>/reset_password', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def reset_employee_pass_route(user_id):
    data = request.get_json(silent=True) or request.form or {}
    new_pass = data.get('new_password', '').strip()
    ok, msg = user_repo.admin_reset_user_password(user_id, new_pass)
    if ok:
        audit_service.record_event(
            action="user.password_reset_by_admin",
            category="admin",
            object_type="user",
            object_id=str(user_id),
            success=True,
            metadata={"user_id": user_id}
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400


@auth_bp.route('/api/auth/emergency_reset', methods=['POST'])
def emergency_reset_route():
    from plagiarism_detector.core.db import reset_admin_with_master_key
    data = request.get_json(silent=True) or request.form or {}
    master_key = data.get('master_key', '').strip()
    new_pass = data.get('new_password', '').strip()
    ok, msg = reset_admin_with_master_key(master_key, new_pass)
    if ok:
        audit_service.record_event(
            action="admin.emergency_reset",
            category="admin",
            success=True
        )
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'error': msg}), 400
