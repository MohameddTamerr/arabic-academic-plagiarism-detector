# -*- coding: utf-8 -*-
from datetime import datetime
import uuid

import pytest

from app import create_app
from app.models.schema import User
from app.repositories import report_repo
from app.repositories.base_repo import get_session
from app.services.certificate_service import build_certificate_payload


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    test_client = app.test_client()
    with get_session() as session:
        user = User(
            username=f"certificate_admin_{uuid.uuid4().hex[:8]}",
            password_hash='test-only',
            full_name='مدير الاعتماد',
            role='system_admin',
            session_version=1,
            is_active=1,
        )
        session.add(user)
        session.commit()
        user_id = user.id
        username = user.username
    with test_client.session_transaction() as session:
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = 'system_admin'
        session['session_version'] = 1
    return test_client


def _save_report(*, review_status):
    report_id = f"certificate_{uuid.uuid4().hex[:12]}"
    report_repo.save_report(
        report_id=report_id,
        title='دور التخطيط الأمني في إدارة الأزمات',
        author='الباحث أحمد محمود',
        category='إدارة الأزمات',
        overall_pct=12.5,
        copied_pct=8.0,
        para_pct=4.5,
        report_dict={
            'specialization': 'إدارة الأزمات والكوارث',
            'degree_type': 'دكتوراه',
            'reference_number': 'RES-2026-009999',
        },
        scan_status='completed',
        review_status=review_status,
    )
    return report_id


def test_finally_accepted_report_certificate_is_dynamic_and_printable(client):
    report_id = _save_report(review_status='final_accepted')

    response = client.get(f'/api/reports/{report_id}/certificate')

    assert response.status_code == 200
    assert response.content_type.startswith('text/html')
    html = response.get_data(as_text=True)
    assert 'دور التخطيط الأمني في إدارة الأزمات' in html
    assert 'الباحث أحمد محمود' in html
    assert 'إدارة الأزمات والكوارث' in html
    assert '12.5%' in html
    assert '87.5%' in html
    assert 'CERT-RES-2026-009999' in html
    assert 'window.print()' in html


def test_certificate_is_rejected_before_final_acceptance(client):
    report_id = _save_report(review_status='preliminary_accepted')

    response = client.get(f'/api/reports/{report_id}/certificate')

    assert response.status_code == 409
    assert 'الاعتماد النهائي' in response.get_json()['error']


def test_certificate_payload_is_stable_and_clamps_percentages():
    approved_at = datetime(2026, 9, 30, 14, 25)
    report = {
        'id': 'report-1',
        'reference_number': 'RES-2026-000001',
        'title': 'عنوان البحث',
        'author': 'اسم الباحث',
        'category': 'قانون',
        'overall_pct': 130,
    }

    payload = build_certificate_payload(report, approved_at=approved_at)
    assert payload['approval_date'] == '2026-09-30'
    assert payload['similarity_pct'] == 100.0
    assert payload['originality_pct'] == 0.0
    assert len(payload['certificate_fingerprint']) == 16

    stored = dict(payload)
    stored['title'] = 'عنوان محفوظ وقت الاعتماد'
    assert build_certificate_payload({'certificate': stored})['title'] == 'عنوان محفوظ وقت الاعتماد'


def test_certificate_controls_are_present_in_both_report_views():
    template = open('templates/index.html', encoding='utf-8').read()
    listing_script = open('static/js/report-list.js', encoding='utf-8').read()

    assert 'id="btn-report-certificate"' in template
    assert 'function openCertificate' in template
    assert 'openCertificate(targetId)' in template
    assert 'openCertificate(report.id)' in listing_script
    assert 'الشهادة' in listing_script
