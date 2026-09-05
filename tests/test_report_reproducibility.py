# -*- coding: utf-8 -*-
"""
حزمة اختبارات استنساخ التقارير وتتبع إصدارات المحرك والمراجع (Report Reproducibility & Versioning Tests):
1. حفظ إصدار المحرك ونموذج التطبيع في لقطة التقرير.
2. حفظ العتبات الفعلية المستخدمة أثناء الفحص.
3. حفظ حالة النموذج الدلالي (معطل/مفعل) بدون أخطاء.
4. حفظ إصدار قاعدة المراجع وبصمتها الحتمية.
5. ثبات لقطة التقرير القديم عند تعديل إعدادات المنظومة اللاحقة.
6. وضوح تمييز التقارير القديمة (Legacy Reports).
7. منع التعديل اليدوي على لقطات الفحص (Immutability).
8. تضمين بيانات الاستنساخ في تصدير HTML.
9. تسجيل أحداث التدقيق المرتبطة باللقطات ونسخ المراجع.
10. التحقق من عدم تسريب أي أسرار في لقطة الإعدادات.
"""

import json
import pytest
from app import create_app, versioning
from app.repositories import report_repo, document_repo
from app.services import snapshot_service, settings_service
from app.repositories.base_repo import get_session
from app.models.snapshot_schema import ReportExecutionSnapshot, ReferenceCorpusVersion
from app.models.audit_schema import AuditLog
from plagiarism_detector.reporting import html_exporter


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_new_report_stores_engine_and_normalization_versions():
    """التقرير الجديد يحفظ تلقائياً إصدار المحرك ونموذج التطبيع المعتمد."""
    rep_id = "test_snap_ver_001"
    settings = {'jaccard_threshold': 0.40, 'tfidf_threshold': 0.45}
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=10,
        research_reference_number="RES-2026-000010",
        settings_used=settings
    )

    snap = snapshot_service.get_report_snapshot(rep_id)
    assert snap['engine_version'] == versioning.ENGINE_VERSION
    assert snap['normalization_version'] == versioning.NORMALIZATION_VERSION
    assert snap['detector_version'] == versioning.DETECTOR_VERSION
    assert snap['report_schema_version'] == versioning.REPORT_SCHEMA_VERSION
    assert snap['is_legacy'] is False


def test_new_report_stores_actual_thresholds_used():
    """التقرير الجديد يحفظ العتبات الفعلية التي تمت بها عملية الفحص بدقة."""
    rep_id = "test_snap_thresh_002"
    custom_settings = {
        'jaccard_threshold': 0.33,
        'tfidf_threshold': 0.52,
        'max_allowed_pages_per_source': 4.0,
        'shingle_size': 6
    }
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=11,
        research_reference_number="RES-2026-000011",
        settings_used=custom_settings
    )

    snap = snapshot_service.get_report_snapshot(rep_id)
    assert snap['jaccard_threshold'] == 0.33
    assert snap['tfidf_threshold'] == 0.52
    assert snap['max_pages_per_source'] == 4.0
    assert snap['shingle_size'] == 6


def test_semantic_disabled_state_persisted_correctly():
    """حالة تعطيل النموذج الدلالي (100% Offline) تُحفظ بدقة دون أخطاء."""
    rep_id = "test_snap_sem_003"
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=12,
        research_reference_number="RES-2026-000012",
        settings_used={'enable_semantic_model': False}
    )

    snap = snapshot_service.get_report_snapshot(rep_id)
    assert snap['semantic_enabled'] is False
    assert snap['semantic_model_identifier'] is None


def test_reference_corpus_version_and_fingerprint_deterministic():
    """إصدار وبصمة قاعدة المراجع تكون حتمية وثابتة لمجموعة المراجع المحددة."""
    fp1, count1 = snapshot_service.compute_corpus_fingerprint()
    ver1, _ = snapshot_service.get_current_reference_corpus_info()

    assert ver1.startswith("REF-")
    assert len(fp1) == 64  # SHA-256 Hex

    # إعادة الحساب بنفس الحالة تعطي نفس البصمة
    fp2, count2 = snapshot_service.compute_corpus_fingerprint()
    assert fp1 == fp2
    assert count1 == count2


def test_changing_active_settings_does_not_change_old_report_snapshot():
    """تعديل إعدادات المنظومة لاحقاً لا يُغيّر العتبات المسجلة في لقطة التقرير القديم."""
    rep_id = "test_snap_historical_004"
    # فحص تقرير في سبتمبر بعتبة 0.35
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=15,
        research_reference_number="RES-2026-000015",
        settings_used={'jaccard_threshold': 0.35, 'tfidf_threshold': 0.35}
    )

    # تغيير إعدادات المنظومة النشطة إلى 0.45
    settings_service.save_settings({'jaccard_threshold': 0.45, 'tfidf_threshold': 0.45})

    # استرجاع لقطة التقرير القديم والتأكد من بقائها 0.35
    snap = snapshot_service.get_report_snapshot(rep_id)
    assert snap['jaccard_threshold'] == 0.35
    assert snap['tfidf_threshold'] == 0.35


def test_legacy_reports_remain_readable_and_marked_as_legacy():
    """التقارير القديمة التي لا تملك لقطة سابقة تظل مقروءة وتُميز بوضوح كـ legacy."""
    rep_id = "legacy_rep_historical_999"
    report_repo.save_report(
        report_id=rep_id,
        title="بحث قديم من الإصدار السابق",
        overall_pct=15.0,
        copied_pct=10.0,
        para_pct=5.0,
        report_dict={'title': 'بحث قديم من الإصدار السابق'}
    )

    rep_data = report_repo.get_report(rep_id)
    assert rep_data is not None
    assert 'snapshot' in rep_data
    snap = rep_data['snapshot']
    assert snap['is_legacy'] is True
    assert 'غير مسجل تفصيلياً' in snap['engine_version']


def test_snapshot_immutability_no_edit_routes(client):
    """لا توجد أي مسارات برمجية تسمح بتعديل لقطات الفحص المحفوظة."""
    headers = {'X-User-Role': 'admin'}
    res_put = client.put('/api/reports/test_snap_001/snapshot', headers=headers, json={'jaccard_threshold': 0.99})
    assert res_put.status_code in (404, 405)


def test_export_includes_reproducibility_metadata():
    """تصدير التقرير إلى HTML يتضمن كافة بيانات الاستنساخ والنسخ والعتبات."""
    rep_dict = {
        'id': 'exp_rep_001',
        'title': 'بحث التحكيم والتصدير',
        'author': 'د. خالد إبراهيم',
        'reference_number': 'RES-2026-000555',
        'overall_pct': 18.0,
        'snapshot': {
            'engine_version': '1.2.0',
            'normalization_version': 'arabic-normalizer-1.0',
            'reference_corpus_version': 'REF-2026-000001',
            'jaccard_threshold': 0.40,
            'tfidf_threshold': 0.40,
            'is_legacy': False
        }
    }

    html_out = html_exporter.export_report_to_html(rep_dict)
    assert 'RES-2026-000555' in html_out
    assert 'v1.2.0' in html_out
    assert 'arabic-normalizer-1.0' in html_out
    assert 'REF-2026-000001' in html_out
    assert 'عتبة التطابق اللفظي' in html_out


def test_audit_event_created_for_snapshot():
    """إنشاء لقطة التقرير يوثق حدث تدقيق report.snapshot_created."""
    rep_id = "audit_snap_rep_007"
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=19,
        research_reference_number="RES-2026-000019",
        settings_used={'jaccard_threshold': 0.40}
    )

    with get_session() as session:
        ev = (
            session.query(AuditLog)
            .filter(AuditLog.action == 'report.snapshot_created', AuditLog.report_id == rep_id)
            .first()
        )
        assert ev is not None
        assert ev.success is True


def test_no_secrets_in_configuration_snapshot():
    """البيانات الوصفية للقطة الفحص لا تحتوي على أي كلمات مرور أو أسرار مشفرة."""
    dirty_settings = {
        'jaccard_threshold': 0.40,
        'secret_key': 'SuperSecretKey123',
        'database_password': 'db_password_xyz'
    }
    rep_id = "test_snap_clean_008"
    snap_obj = snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=20,
        research_reference_number="RES-2026-000020",
        settings_used=dirty_settings
    )

    with get_session() as session:
        snap_row = session.query(ReportExecutionSnapshot).filter(ReportExecutionSnapshot.report_id == rep_id).first()
        cfg_str = snap_row.configuration_snapshot_json
        assert 'SuperSecretKey123' not in cfg_str
        assert 'db_password_xyz' not in cfg_str
        assert 'jaccard_threshold' in cfg_str
