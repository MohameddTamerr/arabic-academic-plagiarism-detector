# -*- coding: utf-8 -*-
"""
حزمة اختبارات نموذج حالات سير العمل المؤسسي (Workflow Status Model Tests):
1. التحقق من القيم الافتراضية لحالتي الفحص التقني والتحكيم الأكاديمي.
2. التحقق من صحة وقانونية انتقالات الفحص (queued -> processing -> completed/failed).
3. التحقق من صحة وقانونية انتقالات التحكيم (pending_review -> preliminary_accepted -> final_accepted).
4. التحقق من رفض الانتقالات غير القانونية عبر الـ Backend (HTTP 400).
5. التحقق من أن اكتمال الفحص بنجاح لا يعني الموافقة الأكاديمية تلقائياً.
6. التحقق من أن الفشل التقني لا يُدرج البحث في قائمة المرفوضات الأكاديمية.
7. التحقق من هجرة السجلات وتوثيق الحالة السابقة والجديدة في سجل التدقيق.
"""

import json
import pytest
from app import create_app
from app.models.research_schema import Research
from app.models.schema import LegacyReport
from app.models.audit_schema import AuditLog
from app.repositories import report_repo, batch_repo
from app.repositories.base_repo import get_session
from app.workflow.statuses import (
    ScanStatus, ReviewStatus, validate_scan_transition, validate_review_transition,
    map_legacy_status, derive_legacy_status
)


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _login_as(client, role):
    with client.session_transaction() as session:
        session['user_id'] = 987654
        session['username'] = f'test_{role}'
        session['role'] = role


def test_new_research_initial_statuses():
    """البحث الجديد يبدأ بحالة فحص queued وحالة تحكيم pending_review."""
    res_id = batch_repo.create_research(
        title="بحث اختبار الحالات الأولية",
        author="د. محمود شريف"
    )
    res_obj = batch_repo.get_research(res_id)
    assert res_obj is not None
    assert res_obj['scan_status'] == ScanStatus.QUEUED.value
    assert res_obj['review_status'] == ReviewStatus.PENDING_REVIEW.value


def test_valid_scan_state_transitions():
    """التحقق من صحة الانتقالات التقنية للفحص."""
    assert validate_scan_transition(ScanStatus.QUEUED.value, ScanStatus.PROCESSING.value) is True
    assert validate_scan_transition(ScanStatus.PROCESSING.value, ScanStatus.COMPLETED.value) is True
    assert validate_scan_transition(ScanStatus.PROCESSING.value, ScanStatus.FAILED.value) is True
    assert validate_scan_transition(ScanStatus.PROCESSING.value, ScanStatus.INTERRUPTED.value) is True
    assert validate_scan_transition(ScanStatus.FAILED.value, ScanStatus.PROCESSING.value) is True
    assert validate_scan_transition(ScanStatus.INTERRUPTED.value, ScanStatus.PROCESSING.value) is True

    # انتقال غير مسموح
    assert validate_scan_transition(ScanStatus.QUEUED.value, ScanStatus.COMPLETED.value) is False


def test_valid_review_state_transitions():
    """التحقق من صحة الانتقالات الإجرائية للتحكيم الأكاديمي."""
    # pending_review -> preliminary_accepted / rejected
    assert validate_review_transition(ReviewStatus.PENDING_REVIEW.value, ReviewStatus.PRELIMINARY_ACCEPTED.value) is True
    assert validate_review_transition(ReviewStatus.PENDING_REVIEW.value, ReviewStatus.REJECTED.value) is True

    # preliminary_accepted -> final_accepted / rejected
    assert validate_review_transition(ReviewStatus.PRELIMINARY_ACCEPTED.value, ReviewStatus.FINAL_ACCEPTED.value) is True
    assert validate_review_transition(ReviewStatus.PRELIMINARY_ACCEPTED.value, ReviewStatus.REJECTED.value) is True

    # انتقال غير مسموح: الاعتماد النهائي حالة منتهية ولا يُسمح بالرجوع المباشر
    assert validate_review_transition(ReviewStatus.FINAL_ACCEPTED.value, ReviewStatus.PRELIMINARY_ACCEPTED.value) is False


def test_completed_scan_does_not_imply_academic_approval(client):
    """اكتمال الفحص التقني بنسبة تشابه منخفضة أو عالية يُبقي حالة التحكيم قيد المراجعة (pending_review)."""
    rep_id = "test_stat_rep_001"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث مكتمل الفحص",
        overall_pct=5.0,
        copied_pct=3.0,
        para_pct=2.0,
        report_dict={'title': 'بحث مكتمل الفحص'},
        scan_status=ScanStatus.COMPLETED.value,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )

    rep_data = report_repo.get_report(rep_id)
    assert rep_data['scan_status'] == ScanStatus.COMPLETED.value
    assert rep_data['review_status'] == ReviewStatus.PENDING_REVIEW.value


def test_high_similarity_does_not_imply_academic_rejection():
    """نسبة الاستلال العالية لا تجعل البحث مرفوضاً تلقائياً بدون قرار تحكيمي بشري صريح."""
    rep_id = "test_stat_rep_high_sim"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث ذو استلال مرتفع",
        overall_pct=85.0,
        copied_pct=70.0,
        para_pct=15.0,
        report_dict={'title': 'بحث ذو استلال مرتفع'},
        scan_status=ScanStatus.COMPLETED.value,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )

    rep_data = report_repo.get_report(rep_id)
    assert rep_data['review_status'] == ReviewStatus.PENDING_REVIEW.value
    assert rep_data['review_status'] != ReviewStatus.REJECTED.value


def test_academic_review_workflow_progression(client):
    """التحقق من تسلسل قرارات التحكيم: قبول مبدئي ثم اعتماد نهائي."""
    rep_id = "test_stat_rep_workflow_seq"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث مسار التحكيم الكامل",
        overall_pct=12.0,
        copied_pct=8.0,
        para_pct=4.0,
        report_dict={'title': 'بحث مسار التحكيم الكامل'},
        scan_status=ScanStatus.COMPLETED.value,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )

    # 1. قبول مبدئي
    _login_as(client, 'reviewer')
    res_init = client.post(f'/api/reports/{rep_id}/initial_accept')
    assert res_init.status_code == 200
    assert res_init.get_json()['review_status'] == ReviewStatus.PRELIMINARY_ACCEPTED.value

    # 2. اعتماد نهائي
    _login_as(client, 'senior_reviewer')
    res_final = client.post(f'/api/reports/{rep_id}/final_accept')
    assert res_final.status_code == 200
    assert res_final.get_json()['review_status'] == ReviewStatus.FINAL_ACCEPTED.value


def test_invalid_review_transition_rejected_by_backend(client):
    """محاولة انتقال تحكيمي غير قانوني من الاعتماد النهائي تُرفض برمجياً (HTTP 400)."""
    rep_id = "test_stat_rep_finalized"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث معتمد نهائياً",
        overall_pct=8.0,
        copied_pct=4.0,
        para_pct=4.0,
        report_dict={'title': 'بحث معتمد نهائياً'},
        scan_status=ScanStatus.COMPLETED.value,
        review_status=ReviewStatus.FINAL_ACCEPTED.value
    )

    # محاولة نقله لقبول مبدئي بعد الاعتماد النهائي
    _login_as(client, 'reviewer')
    res_invalid = client.post(f'/api/reports/{rep_id}/initial_accept')
    assert res_invalid.status_code == 400
    assert 'غير مسموح' in str(res_invalid.get_json().get('error', ''))


def test_technical_failure_does_not_appear_in_academic_rejected_queue():
    """الفشل التقني لا يُدرج البحث في قائمة المرفوضات الأكاديمية."""
    rep_id = "test_stat_tech_failure"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث تعذر استخراج ملفه تقنياً",
        overall_pct=0.0,
        copied_pct=0.0,
        para_pct=0.0,
        report_dict={'title': 'بحث تعذر استخراج ملفه تقنياً'},
        scan_status=ScanStatus.FAILED.value,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )

    rejected_list = report_repo.get_rejected_reports()
    rejected_ids = [r['id'] for r in rejected_list]
    assert rep_id not in rejected_ids


def test_legacy_status_mapping_and_derivation():
    """دوال مواءمة الحالات التاريخية واشتقاق الحالات القديمة تعمل بدقة."""
    s_scan, s_rev = map_legacy_status('قبول مبدئي')
    assert s_scan == ScanStatus.COMPLETED.value
    assert s_rev == ReviewStatus.PRELIMINARY_ACCEPTED.value

    s_scan_err, s_rev_err = map_legacy_status('error')
    assert s_scan_err == ScanStatus.FAILED.value
    assert s_rev_err == ReviewStatus.PENDING_REVIEW.value

    derived = derive_legacy_status(ScanStatus.COMPLETED.value, ReviewStatus.FINAL_ACCEPTED.value)
    assert derived == 'قبول نهائي'


def test_audit_event_contains_previous_and_new_review_status(client):
    """أحداث التحكيم توثق الحالة السابقة والحالة الجديدة بدقة في سجل التدقيق."""
    rep_id = "test_audit_status_transition"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث توثيق حالات التدقيق",
        overall_pct=14.0,
        copied_pct=7.0,
        para_pct=7.0,
        report_dict={'title': 'بحث توثيق حالات التدقيق'},
        scan_status=ScanStatus.COMPLETED.value,
        review_status=ReviewStatus.PENDING_REVIEW.value
    )

    _login_as(client, 'reviewer')
    client.post(f'/api/reports/{rep_id}/reject')

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'review.rejected', AuditLog.report_id == rep_id)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ev is not None
        meta = json.loads(ev.metadata_json)
        assert meta['previous_review_status'] == ReviewStatus.PENDING_REVIEW.value
        assert meta['new_review_status'] == ReviewStatus.REJECTED.value
