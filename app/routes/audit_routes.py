# -*- coding: utf-8 -*-
"""
مسارات سجل التدقيق والمراجعة المؤسسي (Institutional Audit Routes):
- GET /api/admin/audit_logs          → استعلام وتصفية سجلات التدقيق (Admin Only)
- GET /api/admin/audit_logs/<id>     → تفاصيل حدث تدقيق محدد (Admin Only)
"""

from flask import Blueprint, request, jsonify
from app.services import audit_service
from app.security.permissions import Permission
from app.security.authorization import require_permission, get_authenticated_user

audit_bp = Blueprint('audit_bp', __name__)


@audit_bp.route('/api/admin/audit_logs', methods=['GET'])
@require_permission(Permission.AUDIT_VIEW)
def list_audit_logs():
    """
    استرجاع سجلات التدقيق مع الفلترة والتقسيم المكتبي.
    متاح للمستخدمين الذين يملكون صلاحية audit.view (مديرو النظام).
    """
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    username = request.args.get('username')
    role = request.args.get('role')
    action = request.args.get('action')
    category = request.args.get('category')
    ref_num = request.args.get('reference_number') or request.args.get('ref_num')
    success_param = request.args.get('success')
    search = request.args.get('q') or request.args.get('search')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    success = None
    if success_param is not None:
        if success_param.lower() in ('1', 'true', 'yes'):
            success = True
        elif success_param.lower() in ('0', 'false', 'no'):
            success = False

    data = audit_service.query_audit_logs(
        date_from=date_from,
        date_to=date_to,
        username=username,
        role=role,
        action=action,
        category=category,
        research_reference_number=ref_num,
        success=success,
        search=search,
        page=page,
        per_page=per_page
    )

    return jsonify(data)


@audit_bp.route('/api/admin/audit_logs/<event_id>', methods=['GET'])
@require_permission(Permission.AUDIT_VIEW)
def get_audit_log_item(event_id):
    """استرجاع تفاصيل حدث تدقيق محدد (صلاحية audit.view)."""
    event = audit_service.get_audit_event_details(event_id)
    if not event:
        return jsonify({'error': 'سجل التدقيق غير موجود.'}), 404

    return jsonify({'event': event})
