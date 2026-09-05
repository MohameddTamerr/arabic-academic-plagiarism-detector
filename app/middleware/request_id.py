# -*- coding: utf-8 -*-
"""
برمجية وسيطة لمعرف تتبع الطلب السيادي للخادم (Server-Authoritative Request Correlation ID Middleware):
- الخادم هو المصدر المرجعي الحصري لتوليد معرف الطلب الداخلي request_id (UUID4 hex).
- لا يتم استبدال معرف الخادم بأي معرف مرسل من العميل.
- المعرف الخارجي القادم (X-Request-Id أو X-Correlation-Id) يتم التحقق منه وتنقيته وحفظه كمعرف خارجي منفصل external_request_id.
"""

import uuid
import re
from flask import Flask, request, g

_VALID_REQ_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{8,64}$')


def setup_request_id(app: Flask) -> None:
    """تسجيل البرمجية الوسيطة لمعرف الطلب على مستوى التطبيق."""

    @app.before_request
    def before_request_hook():
        # 1. الخادم يولد دائماً المعرف الداخلي المرجعي
        g.request_id = uuid.uuid4().hex

        # 2. التحقق من المعرف الخارجي الاختياري وحفظه بشكل منفصل
        raw_incoming = request.headers.get('X-Request-Id', '').strip() or request.headers.get('X-Correlation-Id', '').strip()
        if raw_incoming and _VALID_REQ_ID_PATTERN.match(raw_incoming):
            g.external_request_id = raw_incoming
        else:
            g.external_request_id = None

    @app.after_request
    def after_request_hook(response):
        if hasattr(g, 'request_id') and g.request_id:
            response.headers['X-Request-Id'] = g.request_id
        if hasattr(g, 'external_request_id') and g.external_request_id:
            response.headers['X-External-Correlation-Id'] = g.external_request_id
        return response
