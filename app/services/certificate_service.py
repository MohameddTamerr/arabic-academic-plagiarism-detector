# -*- coding: utf-8 -*-
"""Build immutable, printable certificate data for finally accepted reports."""

import hashlib
import json
from datetime import datetime
from typing import Any, Optional


def _percentage(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value or 0.0))), 2)
    except (TypeError, ValueError):
        return 0.0


def _display_percentage(value: float) -> str:
    return f"{value:.2f}".rstrip('0').rstrip('.')


def build_certificate_payload(
    report: dict,
    *,
    approved_at: Optional[datetime] = None,
    approved_by: str = '',
) -> dict:
    """Return a stable certificate snapshot derived only from official report data."""
    stored = report.get('certificate')
    if isinstance(stored, dict) and stored.get('schema_version') == '1.0':
        return dict(stored)

    similarity = _percentage(report.get('overall_pct'))
    originality = round(100.0 - similarity, 2)
    reference_number = str(
        report.get('reference_number')
        or report.get('research_reference_number')
        or report.get('id')
        or ''
    ).strip()
    report_id = str(report.get('id') or report.get('report_id') or '').strip()
    approval_date = approved_at
    if approval_date is None:
        stored_date = report.get('finalized_at') or report.get('created_at')
        if isinstance(stored_date, str) and stored_date.strip():
            try:
                approval_date = datetime.fromisoformat(stored_date.strip())
            except ValueError:
                approval_date = None
    approval_date = approval_date or datetime.utcnow()
    specialization = str(
        report.get('specialization')
        or report.get('department')
        or report.get('category')
        or 'عام'
    ).strip()

    payload = {
        'schema_version': '1.0',
        'certificate_number': f"CERT-{reference_number or report_id}",
        'report_id': report_id,
        'reference_number': reference_number,
        'title': str(report.get('title') or 'بحث علمي').strip(),
        'author': str(report.get('author') or 'غير محدد').strip(),
        'specialization': specialization,
        'degree_type': str(report.get('degree_type') or '').strip(),
        'approval_date': approval_date.strftime('%Y-%m-%d'),
        'similarity_pct': similarity,
        'similarity_pct_display': _display_percentage(similarity),
        'originality_pct': originality,
        'originality_pct_display': _display_percentage(originality),
        'review_result': 'مقبولة',
        'decision': 'اعتماد نهائي لنتيجة الفحص',
        'approved_by': str(approved_by or report.get('finalized_by') or '').strip(),
    }
    signature_source = json.dumps(
        {
            key: payload[key]
            for key in (
                'report_id', 'reference_number', 'title', 'author',
                'approval_date', 'similarity_pct', 'originality_pct',
            )
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    payload['certificate_fingerprint'] = hashlib.sha256(signature_source).hexdigest()[:16].upper()
    return payload
