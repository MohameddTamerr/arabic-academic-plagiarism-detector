# -*- coding: utf-8 -*-
"""
خدمة سجل التدقيق والمراجعة المؤسسي (Institutional Audit Trail Service):
- تسجيل وتوثيق العمليات الإدارية والأكاديمية بنمط تراكمي صارم (Append-Only).
- تطبيق أعلى معايير الخصوصية والأمان عبر استبعاد وحجب أي كلمات مرور أو هاشات أو نصوص كاملة للمستندات.
- توفير الاستعلامات والفلترة السريعة وتفاصيل الأحداث للوحة تدقيق مدير النظام.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Any
from flask import has_request_context, request, g

from app.models.audit_schema import AuditLog
from app.repositories.base_repo import get_session

logger = logging.getLogger(__name__)

# قائمة الكلمات المحظورة التي يجب حجبها تماماً من أي بيانات وصفية
SENSITIVE_KEYS_BLACKLIST = {
    'password', 'old_password', 'new_password', 'password_hash', 'hash',
    'token', 'secret', 'secret_key', 'csrf_token', 'cookie', 'session',
    'full_text', 'raw_text', 'text_content', 'segments', 'evidence_text'
}


def sanitize_metadata(data: Optional[dict]) -> dict:
    """
    تنقية وتطهير البيانات الوصفية لمنع تسريب كلمات المرور أو النصوص الكاملة للمستندات.
    """
    if not data or not isinstance(data, dict):
        return {}

    sanitized = {}
    for key, val in data.items():
        k_lower = str(key).lower()
        # فحص الكلمات الحساسة
        if any(bad in k_lower for bad in SENSITIVE_KEYS_BLACKLIST):
            sanitized[key] = '[REDACTED]'
            continue

        if isinstance(val, dict):
            sanitized[key] = sanitize_metadata(val)
        elif isinstance(val, list):
            sanitized[key] = [
                sanitize_metadata(item) if isinstance(item, dict)
                else (str(item)[:200] if isinstance(item, str) and len(str(item)) > 200 else item)
                for item in val
            ]
        elif isinstance(val, str):
            # منع تخزين النصوص الطويلة للمستندات في سجل التدقيق
            if len(val) > 500:
                sanitized[key] = val[:500] + '... [TRUNCATED]'
            else:
                sanitized[key] = val
        else:
            sanitized[key] = val

    return sanitized


def get_current_request_context() -> dict:
    """استخراج بيانات الطلب وسياق المستخدم تلقائياً إن وجد طلب HTTP نشط."""
    ctx = {
        'user_id': None,
        'username': 'system',
        'role': 'system',
        'request_id': '',
        'ip_address': ''
    }

    if has_request_context():
        # Request Correlation ID
        req_id = request.headers.get('X-Request-Id') or request.headers.get('X-Correlation-Id') or ''
        if not req_id and hasattr(g, 'request_id'):
            req_id = g.request_id
        if not req_id:
            req_id = str(uuid.uuid4())[:8]
        ctx['request_id'] = req_id

        # IP Address
        ctx['ip_address'] = request.remote_addr or ''

        # User snapshot from session / headers / g
        if hasattr(g, 'current_user') and g.current_user:
            u = g.current_user
            ctx['user_id'] = getattr(u, 'id', None) or u.get('id')
            ctx['username'] = getattr(u, 'username', '') or u.get('username', 'system')
            ctx['role'] = getattr(u, 'role', '') or u.get('role', '')
        else:
            header_user = request.headers.get('X-User-Name')
            header_role = request.headers.get('X-User-Role')
            header_uid = request.headers.get('X-User-Id')
            if header_user:
                ctx['username'] = header_user
                ctx['role'] = header_role or 'employee'
                try:
                    ctx['user_id'] = int(header_uid) if header_uid else None
                except (ValueError, TypeError):
                    pass

    return ctx


def record_event(
    action: str,
    category: str,
    user: Optional[Any] = None,
    object_type: str = '',
    object_id: str = '',
    research_id: Optional[int] = None,
    research_reference_number: str = '',
    batch_id: Optional[str] = None,
    report_id: Optional[str] = None,
    success: bool = True,
    failure_reason_code: str = '',
    metadata: Optional[dict] = None,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None
) -> str:
    """
    تسجيل حدث تدقيق رسمي في قاعدة البيانات.
    يُعيد event_id المولَّد للحدث.
    """
    event_id = str(uuid.uuid4())
    req_ctx = get_current_request_context()

    # تحديد هوية المستخدم
    uid = None
    uname = req_ctx['username']
    urole = req_ctx['role']

    if user:
        if isinstance(user, dict):
            uid = user.get('id')
            uname = user.get('username') or uname
            urole = user.get('role') or urole
        else:
            uid = getattr(user, 'id', None)
            uname = getattr(user, 'username', uname)
            urole = getattr(user, 'role', urole)
    elif req_ctx['user_id'] is not None:
        uid = req_ctx['user_id']

    # تنقية البيانات الوصفية
    clean_meta = sanitize_metadata(metadata or {})
    meta_json = json.dumps(clean_meta, ensure_ascii=False)

    final_req_id = request_id or req_ctx['request_id'] or str(uuid.uuid4())[:8]
    final_ip = ip_address or req_ctx['ip_address'] or ''

    try:
        with get_session() as session:
            event = AuditLog(
                event_id=event_id,
                created_at=datetime.utcnow(),
                user_id=uid,
                username_snapshot=uname or 'system',
                role_snapshot=urole or '',
                action=action,
                category=category,
                object_type=object_type,
                object_id=str(object_id) if object_id else '',
                research_id=research_id,
                research_reference_number=research_reference_number or '',
                batch_id=batch_id,
                report_id=report_id,
                success=success,
                failure_reason_code=failure_reason_code or '',
                request_id=final_req_id,
                ip_address=final_ip,
                metadata_json=meta_json
            )
            session.add(event)
            session.flush()

        logger.info(f"[AUDIT] {action} | user={uname} ({urole}) | ref={research_reference_number} | success={success} | event={event_id}")
        return event_id
    except Exception as e:
        logger.error(f"فشل تسجيل حدث التدقيق ({action}): {e}", exc_info=True)
        # في العمليات الحساسة نرفع الخطأ، وفي العمليات العادية نضمن عدم انهيار المنظومة
        if category in ('admin', 'auth', 'review', 'backup'):
            raise
        return event_id


def query_audit_logs(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    action: Optional[str] = None,
    category: Optional[str] = None,
    research_reference_number: Optional[str] = None,
    success: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20
) -> dict:
    """
    استرجاع سجلات التدقيق مع الفلترة والتقسيم المكتبي (Server-Side Pagination).
    """
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    with get_session() as session:
        query = session.query(AuditLog)

        if category:
            query = query.filter(AuditLog.category == category.strip())
        if action:
            query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
        if username:
            query = query.filter(AuditLog.username_snapshot.ilike(f"%{username.strip()}%"))
        if role:
            query = query.filter(AuditLog.role_snapshot == role.strip())
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if research_reference_number:
            query = query.filter(AuditLog.research_reference_number.ilike(f"%{research_reference_number.strip()}%"))
        if success is not None:
            query = query.filter(AuditLog.success == success)

        if date_from:
            try:
                dt_from = datetime.strptime(date_from.strip(), '%Y-%m-%d')
                query = query.filter(AuditLog.created_at >= dt_from)
            except ValueError:
                pass

        if date_to:
            try:
                dt_to = datetime.strptime(date_to.strip() + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                query = query.filter(AuditLog.created_at <= dt_to)
            except ValueError:
                pass

        if search:
            clean_search = search.strip()
            query = query.filter(
                (AuditLog.action.ilike(f"%{clean_search}%")) |
                (AuditLog.username_snapshot.ilike(f"%{clean_search}%")) |
                (AuditLog.research_reference_number.ilike(f"%{clean_search}%")) |
                (AuditLog.object_id.ilike(f"%{clean_search}%")) |
                (AuditLog.event_id.ilike(f"%{clean_search}%"))
            )

        total = query.count()
        total_pages = max(1, (total + per_page - 1) // per_page)

        events = (
            query
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        results = []
        for e in events:
            try:
                meta = json.loads(e.metadata_json) if e.metadata_json else {}
            except Exception:
                meta = {}

            results.append({
                'id': e.id,
                'event_id': e.event_id,
                'created_at': e.created_at.strftime('%Y-%m-%d %H:%M:%S') if e.created_at else '',
                'user_id': e.user_id,
                'username': e.username_snapshot,
                'role': e.role_snapshot,
                'action': e.action,
                'category': e.category,
                'object_type': e.object_type,
                'object_id': e.object_id,
                'research_id': e.research_id,
                'research_reference_number': e.research_reference_number,
                'batch_id': e.batch_id,
                'report_id': e.report_id,
                'success': e.success,
                'failure_reason_code': e.failure_reason_code,
                'request_id': e.request_id,
                'ip_address': e.ip_address,
                'metadata': meta
            })

        return {
            'items': results,
            'events': results,
            'total_items': total,
            'total': total,
            'page': page,
            'page_size': per_page,
            'per_page': per_page,
            'total_pages': total_pages
        }


def get_audit_event_details(event_id: str) -> Optional[dict]:
    """استرجاع التفاصيل الكاملة لحدث تدقيق محدد بمعرفه الفريد."""
    with get_session() as session:
        e = session.query(AuditLog).filter(AuditLog.event_id == event_id.strip()).first()
        if not e:
            return None
        try:
            meta = json.loads(e.metadata_json) if e.metadata_json else {}
        except Exception:
            meta = {}
        return {
            'id': e.id,
            'event_id': e.event_id,
            'created_at': e.created_at.strftime('%Y-%m-%d %H:%M:%S') if e.created_at else '',
            'user_id': e.user_id,
            'username': e.username_snapshot,
            'role': e.role_snapshot,
            'action': e.action,
            'category': e.category,
            'object_type': e.object_type,
            'object_id': e.object_id,
            'research_id': e.research_id,
            'research_reference_number': e.research_reference_number,
            'batch_id': e.batch_id,
            'report_id': e.report_id,
            'success': e.success,
            'failure_reason_code': e.failure_reason_code,
            'request_id': e.request_id,
            'ip_address': e.ip_address,
            'metadata': meta
        }
