# -*- coding: utf-8 -*-
"""
مسارات إدارة المستخدمين المؤسسية (Admin User Management Routes):
- استعراض وبحث قائمة المستخدمين مع الحقول الآمنة والإحصائيات.
- إضافة مستخدمين جدد مع ضبط وتأمين الأدوار ومنع تصعيد الصلاحيات (Privilege Escalation Protection).
- تعديل البيانات الآمنة للملف الشخصي وتحديث الأدوار.
- تفعيل وتعطيل الحسابات مع إبطال الجلسات النشطة فوراً.
- إعادة تعيين كلمات المرور من قبل المدير وإلغاء/إعادة طلب استرداد الحسابات.
- توثيق كافة الأحداث في سجل التدقيق الأمني (Audit Trail).
"""

from flask import Blueprint, request, jsonify

from app.security.permissions import Permission, Role, normalize_role, ROLE_LABELS_AR
from app.security.authorization import require_permission, get_authenticated_user
from app.repositories import user_repo
from app.services import audit_service, recovery_service
from app.errors.error_codes import ErrorCode
from app.utils.pagination import get_pagination_params, format_paginated_response

user_bp = Blueprint('user_bp', __name__)

# تراتبية الأدوار للتحقق من منع تصعيد الصلاحيات (Role Hierarchy)
ROLE_HIERARCHY = {
    Role.EMPLOYEE: 1,
    Role.DATA_ENTRY: 1,
    Role.REVIEWER: 2,
    Role.SENIOR_REVIEWER: 3,
    Role.UNIT_MANAGER: 4,
    Role.SYSTEM_ADMIN: 5,
    Role.LEGACY_ADMIN: 5
}


def _can_assign_role(actor_role: str, target_role: str) -> bool:
    """التحقق مما إذا كان الفاعل يملك الأهلية لإسناد أو تعديل الدور المستهدف."""
    norm_actor = normalize_role(actor_role)
    norm_target = normalize_role(target_role)

    actor_rank = ROLE_HIERARCHY.get(norm_actor, 0)
    target_rank = ROLE_HIERARCHY.get(norm_target, 0)

    # مدير النظام هو الوحيد القادر على إسناد دور مدير النظام
    if norm_target in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN) and norm_actor not in (Role.SYSTEM_ADMIN, Role.LEGACY_ADMIN):
        return False

    return actor_rank >= target_rank


@user_bp.route('/api/admin/users', methods=['GET'])
@user_bp.route('/api/users', methods=['GET'])
@require_permission(Permission.USERS_VIEW)
def list_users():
    """استرجاع وبحث قائمة المستخدمين مع التقسيم والفلترة ونطاق الوحدة."""
    params = get_pagination_params(
        default_size=25,
        max_size=100,
        allowed_sort_fields=['id', 'username', 'full_name', 'role', 'created_at']
    )

    actor = get_authenticated_user()
    actor_role = normalize_role(actor.get('role') if actor else 'employee')

    role_filter = request.args.get('role')
    status_filter = request.args.get('status')
    dept_filter = request.args.get('department')

    if actor_role == Role.UNIT_MANAGER and actor and actor.get('department'):
        dept_filter = actor.get('department')

    is_active = None
    if status_filter in ('active', '1', 'نشط'):
        is_active = 1
    elif status_filter in ('disabled', '0', 'معطل', 'موقوف'):
        is_active = 0

    rec_status = request.args.get('recovery_status')

    items, total_count = user_repo.search_users_paginated(
        query=params['q'],
        role=role_filter,
        department=dept_filter,
        is_active=is_active,
        recovery_status=rec_status,
        page=params['page'],
        per_page=params['page_size']
    )

    return jsonify(format_paginated_response(
        items=items,
        total_items=total_count,
        page=params['page'],
        page_size=params['page_size'],
        legacy_key='users'
    ))


@user_bp.route('/api/admin/users/stats', methods=['GET'])
@user_bp.route('/api/users/stats', methods=['GET'])
@require_permission(Permission.USERS_VIEW)
def get_user_stats():
    """استرجاع إحصائيات بطاقات إدارة المستخدمين."""
    stats = user_repo.get_user_management_stats()
    return jsonify(stats)


@user_bp.route('/api/admin/users/<int:user_id>', methods=['GET'])
@user_bp.route('/api/users/<int:user_id>', methods=['GET'])
@require_permission(Permission.USERS_VIEW)
def get_user_detail(user_id):
    """استرجاع بيانات مستخدم محدد بالحقول الآمنة ونطاق الوحدة."""
    user = user_repo.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    actor = get_authenticated_user()
    actor_role = normalize_role(actor.get('role') if actor else 'employee')
    if actor_role == Role.UNIT_MANAGER and actor:
        actor_dept = (actor.get('department') or '').strip().lower()
        user_dept = (user.get('department') or '').strip().lower()
        if actor_dept and user_dept and actor_dept != user_dept:
            return jsonify({'error': 'غير مصرح: لا تملك صلاحية الوصول لبيانات مستخدم خارج وحدتك', 'code': ErrorCode.AUTH_FORBIDDEN}), 403

    return jsonify(user)


@user_bp.route('/api/admin/users', methods=['POST'])
@user_bp.route('/api/users', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def create_user():
    """إضافة مستخدم جديد مع فحص منع تصعيد الصلاحيات."""
    data = request.get_json(silent=True) or request.form or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    full_name = (data.get('full_name') or '').strip()
    role = (data.get('role') or 'employee').strip()
    department = (data.get('department') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    must_change_password = 1 if data.get('must_change_password') in (1, '1', True, 'true') else 0
    must_enroll_recovery = 1 if data.get('must_enroll_recovery') in (1, '1', True, 'true') else 0

    if not username or not password or not full_name:
        return jsonify({'error': 'اسم المستخدم وكلمة المرور والاسم الكامل حقول مطلوبة', 'code': ErrorCode.VALIDATION_ERROR}), 400

    actor = get_authenticated_user()
    actor_role = actor.get('role') if actor else 'employee'
    norm_target_role = normalize_role(role)

    # حساب الموظف يبدأ دائماً بكلمة مرور مؤقتة، ثم يختار الموظف كلمة
    # دائمة وبطاقة استرداد خاصة به في أول تسجيل دخول.
    is_employee_onboarding = norm_target_role == Role.EMPLOYEE
    if is_employee_onboarding:
        must_change_password = 1
        must_enroll_recovery = 1

    # منع تصعيد الصلاحيات
    if not _can_assign_role(actor_role, norm_target_role):
        audit_service.record_event(
            action="authorization.privilege_escalation_denied",
            category="security",
            user=actor,
            success=False,
            failure_reason_code="PRIVILEGE_ESCALATION_DENIED",
            metadata={'attempted_role': norm_target_role, 'actor_role': actor_role}
        )
        return jsonify({
            'error': f'غير مصرح: لا تملك الصلاحية الكافية لإنشاء حساب بدور ({ROLE_LABELS_AR.get(norm_target_role, norm_target_role)})',
            'code': ErrorCode.AUTH_FORBIDDEN
        }), 403

    success, msg = user_repo.add_user(
        username=username,
        password=password,
        full_name=full_name,
        role=norm_target_role,
        department=department,
        phone_number=phone_number,
        must_change_password=must_change_password,
        must_enroll_recovery=must_enroll_recovery,
        enforce_policy=False if is_employee_onboarding else None
    )

    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    created_u = user_repo.get_user_by_username(username)
    new_user_id = created_u['id'] if created_u else None

    audit_service.record_event(
        action="USER_CREATED",
        category="users",
        user=actor,
        object_type="user",
        object_id=str(new_user_id or username),
        success=True,
        metadata={
            'username': username,
            'full_name': full_name,
            'role': norm_target_role,
            'department': department,
            'must_change_password': must_change_password,
            'must_enroll_recovery': must_enroll_recovery
        }
    )

    return jsonify({
        'success': True,
        'message': msg,
        'user_id': new_user_id,
        'username': username
    }), 201


@user_bp.route('/api/admin/users/<int:user_id>', methods=['PUT', 'POST'])
@user_bp.route('/api/users/<int:user_id>', methods=['PUT', 'POST'])
@require_permission(Permission.USERS_MANAGE)
def update_user(user_id):
    """تعديل بيانات الملف الشخصي ودور المستخدم."""
    data = request.get_json(silent=True) or request.form or {}
    full_name = data.get('full_name')
    role = data.get('role')
    department = data.get('department')
    phone_number = data.get('phone_number')

    target_user = user_repo.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    actor = get_authenticated_user()
    actor_role = actor.get('role') if actor else 'employee'

    if role:
        norm_target_role = normalize_role(role)
        # منع تصعيد الصلاحيات
        if not _can_assign_role(actor_role, norm_target_role) or not _can_assign_role(actor_role, target_user['role']):
            audit_service.record_event(
                action="authorization.privilege_escalation_denied",
                category="security",
                user=actor,
                success=False,
                failure_reason_code="PRIVILEGE_ESCALATION_DENIED",
                metadata={'attempted_role': norm_target_role, 'actor_role': actor_role, 'target_user_id': user_id}
            )
            return jsonify({
                'error': f'غير مصرح: لا تملك الصلاحية لتغيير الدور إلى ({ROLE_LABELS_AR.get(norm_target_role, norm_target_role)})',
                'code': ErrorCode.AUTH_FORBIDDEN
            }), 403

    success, msg, changes = user_repo.update_user_profile_fields(
        user_id=user_id,
        full_name=full_name,
        role=role,
        department=department,
        phone_number=phone_number
    )

    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    if 'role' in changes:
        audit_service.record_event(
            action="USER_ROLE_CHANGED",
            category="users",
            user=actor,
            object_type="user",
            object_id=str(user_id),
            success=True,
            metadata={
                'username': target_user['username'],
                'old_role': changes['role']['old'],
                'new_role': changes['role']['new']
            }
        )

    audit_service.record_event(
        action="USER_PROFILE_UPDATED",
        category="users",
        user=actor,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={
            'username': target_user['username'],
            'changes': list(changes.keys())
        }
    )

    return jsonify({'success': True, 'message': msg, 'changes': changes})


@user_bp.route('/api/admin/users/<int:user_id>/toggle_status', methods=['POST'])
@user_bp.route('/api/users/<int:user_id>/status', methods=['PATCH', 'POST'])
@require_permission(Permission.USERS_MANAGE)
def toggle_user_status(user_id):
    """تفعيل أو تعطيل حساب المستخدم."""
    actor = get_authenticated_user()
    if actor and actor.get('id') == user_id:
        return jsonify({'error': 'لا يمكن تعطيل حسابك الشخصي الحالي', 'code': ErrorCode.VALIDATION_ERROR}), 400

    target_user = user_repo.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    data = request.get_json(silent=True) or request.form or {}
    if 'is_active' in data:
        new_active = 1 if data['is_active'] in (1, '1', True, 'true') else 0
    else:
        new_active = 0 if target_user['is_active'] == 1 else 1

    success, msg = user_repo.set_user_active_status(user_id, new_active)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    event_name = "USER_ENABLED" if new_active == 1 else "USER_DISABLED"
    audit_service.record_event(
        action=event_name,
        category="users",
        user=actor,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={'username': target_user['username'], 'is_active': new_active}
    )

    return jsonify({'success': True, 'message': msg, 'is_active': new_active})


@user_bp.route('/api/admin/users/<int:user_id>/reset_password', methods=['POST'])
@user_bp.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@require_permission(Permission.USER_PASSWORD_ADMIN_RESET)
def admin_reset_password(user_id):
    """إعادة تعيين كلمة مرور مستخدم من قبل المدير المعتمد."""
    data = request.get_json(silent=True) or request.form or {}
    new_password = (data.get('new_password') or data.get('password') or '').strip()

    if not new_password:
        return jsonify({'error': 'كلمة المرور الجديدة مطلوبة', 'code': ErrorCode.VALIDATION_ERROR}), 400

    target_user = user_repo.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    actor = get_authenticated_user()
    success, msg = user_repo.admin_reset_user_password(user_id, new_password)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    audit_service.record_event(
        action="USER_PASSWORD_ADMIN_RESET",
        category="users",
        user=actor,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={'username': target_user['username']}
    )

    return jsonify({'success': True, 'message': msg})


@user_bp.route('/api/admin/users/<int:user_id>/recovery/revoke', methods=['POST'])
@user_bp.route('/api/users/<int:user_id>/recovery/revoke', methods=['POST'])
@require_permission(Permission.USER_RECOVERY_REVOKE)
def revoke_user_recovery(user_id):
    """إلغاء بطاقة اعتماد الاسترداد لمستخدم."""
    target_user = user_repo.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    actor = get_authenticated_user()
    success, msg = recovery_service.revoke_recovery_credential(user_id, actor_user=actor)
    if not success:
        return jsonify({'error': msg, 'code': ErrorCode.VALIDATION_ERROR}), 400

    audit_service.record_event(
        action="USER_RECOVERY_REVOKED",
        category="users",
        user=actor,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={'username': target_user['username']}
    )

    return jsonify({'success': True, 'message': msg})


@user_bp.route('/api/admin/users/<int:user_id>/recovery/require_reenroll', methods=['POST'])
@require_permission(Permission.USERS_MANAGE)
def require_user_recovery_reenroll(user_id):
    """إلغاء بطاقة الاسترداد الحالية وإلزام المستخدم بإعادة إعداد الاسترداد عند الدخول القادم."""
    target_user = user_repo.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود', 'code': ErrorCode.USER_NOT_FOUND}), 404

    actor = get_authenticated_user()
    # إلغاء البطاقة إن وجدت
    recovery_service.revoke_recovery_credential(user_id, actor_user=actor)

    # تعيين راية must_enroll_recovery
    from app.repositories.base_repo import get_session
    from app.models.schema import User
    with get_session() as session:
        u = session.query(User).filter(User.id == user_id).first()
        if u:
            u.must_enroll_recovery = 1
            u.session_version = getattr(u, 'session_version', 1) + 1

    audit_service.record_event(
        action="USER_RECOVERY_REENROLL_REQUIRED",
        category="users",
        user=actor,
        object_type="user",
        object_id=str(user_id),
        success=True,
        metadata={'username': target_user['username']}
    )

    return jsonify({'success': True, 'message': f'تم إلزام المستخدم {target_user["username"]} بإعادة إعداد بطاقة الاسترداد'})
