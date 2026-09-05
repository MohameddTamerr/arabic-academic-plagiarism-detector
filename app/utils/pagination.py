# -*- coding: utf-8 -*-
"""
أداة إدارة وتقسيم الصفحات الموحدة (Standard Server-Side Pagination Utility):
- معالجة معاملات التقسيم والترتيب بأمان مع فرض حدود قصوى صارمة.
- التحقق من قوائم الأعمدة المسموحة للترتيب (Sorting Allowlist) لمنع حقن الاستعلامات.
- توحيد بنية الاستجابة JSON عبر كافة مسارات النظام مع المحافظة على التوافقية الموروثة.
"""

from typing import Dict, Any, List, Optional
from math import ceil
from flask import request


# الحدود الافتراضية والقصوى لتقسيم الصفحات
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def get_pagination_params(
    default_size: int = DEFAULT_PAGE_SIZE,
    max_size: int = MAX_PAGE_SIZE,
    allowed_sort_fields: Optional[List[str]] = None,
    default_sort: str = 'created_at',
    default_order: str = 'desc'
) -> Dict[str, Any]:
    """
    استخراج معاملات التقسيم والترتيب من الـ Query Parameters بأمان:
    - page: رقم الصفحة (افتراضي 1، أقل قيمة 1)
    - page_size / per_page: حجم الصفحة (افتراضي 25، حد أقصى 100)
    - sort: حقل الترتيب (يتم التحقق منه مقابل allowed_sort_fields)
    - order: اتجاه الترتيب (asc أو desc)
    - q / search: نص البحث المدخل
    """
    # 1. رقم الصفحة
    try:
        page = int(request.args.get('page', DEFAULT_PAGE))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    # 2. حجم الصفحة (دعم page_size و per_page)
    try:
        raw_size = request.args.get('page_size') or request.args.get('per_page')
        page_size = int(raw_size) if raw_size is not None else default_size
        if page_size < 1:
            page_size = default_size
        elif page_size > max_size:
            page_size = max_size
    except (ValueError, TypeError):
        page_size = default_size

    # 3. الترتيب الآمن
    sort_field = request.args.get('sort', default_sort).strip()
    if allowed_sort_fields and sort_field not in allowed_sort_fields:
        sort_field = default_sort

    raw_order = request.args.get('order', default_order).strip().lower()
    order = 'asc' if raw_order in ('asc', 'ascending', '1') else 'desc'

    # 4. نص البحث والتواريخ
    q = (request.args.get('q') or request.args.get('search') or '').strip()
    # الحد الأقصى لطول نص البحث
    if len(q) > 255:
        q = q[:255]

    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # 5. معاملات التصفح بالمفاتيح للمجموعات الضخمة (Keyset / Cursor Pagination)
    after_id = None
    before_id = None
    try:
        raw_after = request.args.get('after_id') or request.args.get('cursor')
        if raw_after is not None:
            after_id = int(raw_after)
    except (ValueError, TypeError):
        after_id = None

    try:
        raw_before = request.args.get('before_id')
        if raw_before is not None:
            before_id = int(raw_before)
    except (ValueError, TypeError):
        before_id = None

    return {
        'page': page,
        'page_size': page_size,
        'sort': sort_field,
        'order': order,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'after_id': after_id,
        'before_id': before_id,
        'offset': (page - 1) * page_size,
        'limit': page_size
    }


def format_paginated_response(
    items: List[Any],
    total_items: int,
    page: int,
    page_size: int,
    extra_meta: Optional[Dict[str, Any]] = None,
    legacy_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    بناء استجابة JSON مقسمة وموحدة تدعم التصفح التقليدي والتصفح بالمفاتيح (Keyset/Cursor):
    """
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1
    if total_pages < 1:
        total_pages = 1

    first_item_id = items[0].get('id') if items and isinstance(items[0], dict) and 'id' in items[0] else None
    last_item_id = items[-1].get('id') if items and isinstance(items[-1], dict) and 'id' in items[-1] else None

    response = {
        'items': items,
        'page': page,
        'page_size': page_size,
        'total_items': total_items,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1,
        'first_id': first_item_id,
        'last_id': last_item_id,
        'next_cursor': last_item_id if page < total_pages else None,
        'prev_cursor': first_item_id if page > 1 else None
    }

    # دعم المفاتيح الموروثة للواجهات السابقة مثل papers أو events
    if legacy_key:
        response[legacy_key] = items
        response['total'] = total_items
        response['per_page'] = page_size

    if extra_meta:
        response.update(extra_meta)

    return response

