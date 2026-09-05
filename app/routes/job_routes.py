# -*- coding: utf-8 -*-
"""
مسارات واجهة برمجة التطبيقات لإدارة ومراقبة طابور المهام (Job & Queue Management Routes):
- استعراض وتصفية مهام الطابور الخلفي (queued, running, completed, failed, etc.).
- تفاصيل وتقدم المهمة مع عزل الصلاحيات وحماية الخصوصية المؤسسية.
- الإلغاء التعاوني المنضبط وإعادة المحاولة اليدوية للمهام المنقطعة أو الفاشلة.
- إحصائيات الأداء والتزامن وسعة المعالجة للوحة الإدارة والتشغيل.
"""

import logging
from flask import Blueprint, request, jsonify, g

from app.services import job_queue_service, audit_service
from app.services.job_queue_service import JobType, JobStatus
from app.security.permissions import Permission
from app.security.authorization import (
    require_authenticated, require_permission, get_authenticated_user, has_permission
)
from app.errors.error_codes import ErrorCode
from plagiarism_detector.reporting.report_builder import trigger_async_index_rebuild

logger = logging.getLogger(__name__)

job_bp = Blueprint('job_routes', __name__, url_prefix='/api/jobs')


@job_bp.route('', methods=['GET'])
@require_permission(Permission.JOB_VIEW)
def list_jobs_endpoint():
    """
    استرجاع قائمة المهام في الطابور مع الفرز والترقيم.
    المستخدم العادي يشاهد مهامه فقط، بينما أصحاب صلاحية job.view_all يشاهدون كل المهام.
    """
    user = get_authenticated_user()
    status_filter = request.args.get('status')
    job_type_filter = request.args.get('job_type')
    
    try:
        limit = min(max(int(request.args.get('limit', 50)), 1), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        limit, offset = 50, 0

    can_view_all = has_permission(user, Permission.JOB_VIEW_ALL)

    requested_by = None if can_view_all else (user.get('username') if user else '')

    items, total = job_queue_service.list_jobs(
        status=status_filter,
        job_type=job_type_filter,
        requested_by=requested_by,
        limit=limit,
        offset=offset
    )

    return jsonify({
        'success': True,
        'items': items,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200


@job_bp.route('/<job_id>', methods=['GET'])
@require_permission(Permission.JOB_VIEW)
def get_job_endpoint(job_id: str):
    """استرجاع بيانات ومرحلة تقدم مهمة محددة."""
    user = get_authenticated_user()
    job = job_queue_service.get_job(job_id)
    if not job:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.JOB_NOT_FOUND,
            'message': 'المهمة المطلوبة غير موجودة.'
        }), 404

    can_view_all = has_permission(user, Permission.JOB_VIEW_ALL)

    if not can_view_all and job.get('requested_by') and job.get('requested_by') != (user.get('username') if user else ''):
        return jsonify({
            'success': False,
            'error_code': ErrorCode.AUTH_FORBIDDEN,
            'message': 'غير مصرح لك باستعراض هذه المهمة.'
        }), 403

    return jsonify({
        'success': True,
        'job': job
    }), 200


@job_bp.route('/<job_id>/cancel', methods=['POST'])
@require_permission(Permission.JOB_VIEW)
def cancel_job_endpoint(job_id: str):
    """طلب إلغاء مهمة تعاونياً."""
    user = get_authenticated_user()
    job = job_queue_service.get_job(job_id)
    if not job:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.JOB_NOT_FOUND,
            'message': 'المهمة المطلوبة غير موجودة.'
        }), 404

    can_cancel_any = has_permission(user, Permission.JOB_CANCEL)
    is_owner = (job.get('requested_by') == (user.get('username') if user else ''))

    if not can_cancel_any and not is_owner:
        return jsonify({
            'success': False,
            'error_code': ErrorCode.AUTH_FORBIDDEN,
            'message': 'غير مصرح لك بإلغاء هذه المهمة.'
        }), 403

    data = request.get_json(silent=True) or {}
    reason = data.get('reason', 'طلب المستخدم')
    actor = user.get('username', 'system') if user else 'system'

    success, msg, err_code = job_queue_service.request_job_cancellation(
        job_id=job_id,
        actor=actor,
        reason=reason
    )

    if not success:
        return jsonify({
            'success': False,
            'error_code': err_code or ErrorCode.JOB_CANCEL_NOT_ALLOWED,
            'message': msg
        }), 400

    audit_service.record_event(
        action="job.cancelled",
        category="system",
        object_type="job_record",
        object_id=job_id,
        user=user,
        success=True,
        metadata={'reason': reason, 'job_type': job.get('job_type')}
    )

    return jsonify({
        'success': True,
        'message': msg
    }), 200


@job_bp.route('/<job_id>/retry', methods=['POST'])
@require_permission(Permission.JOB_RETRY)
def retry_job_endpoint(job_id: str):
    """إعادة تشغيل مهمة فاشلة أو منقطعة يدوياً."""
    user = get_authenticated_user()
    actor = user.get('username', 'admin') if user else 'admin'

    success, msg, err_code = job_queue_service.retry_job_manually(job_id=job_id, actor=actor)
    if not success:
        return jsonify({
            'success': False,
            'error_code': err_code or ErrorCode.SCAN_FAILED,
            'message': msg
        }), 400

    audit_service.record_event(
        action="job.retried",
        category="system",
        object_type="job_record",
        object_id=job_id,
        user=user,
        success=True
    )

    return jsonify({
        'success': True,
        'message': msg
    }), 200


@job_bp.route('/stats', methods=['GET'])
@require_permission(Permission.JOB_VIEW)
def get_queue_stats_endpoint():
    """استرجاع إحصائيات طابور المعالجة والتزامن."""
    stats = job_queue_service.get_queue_stats()
    return jsonify({
        'success': True,
        'stats': stats
    }), 200


@job_bp.route('/rebuild-index', methods=['POST'])
@require_permission(Permission.REFERENCE_CORPUS_MANAGE)
def trigger_index_rebuild_endpoint():
    """جدولة إعادة بناء فهرس الاسترجاع في الخلفية بشكل غير متزامن."""
    user = get_authenticated_user()
    actor = user.get('username', 'admin') if user else 'admin'
    data = request.get_json(silent=True) or {}
    corpus_version = data.get('corpus_version')

    job_id = trigger_async_index_rebuild(target_corpus_version=corpus_version, requested_by=actor)

    audit_service.record_event(
        action="reference.index_rebuild_triggered",
        category="reference",
        object_type="job_record",
        object_id=job_id,
        user=user,
        success=True,
        metadata={'target_corpus_version': corpus_version}
    )

    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': 'تمت جدولة إعادة بناء الفهرس بنجاح.'
    }), 202
