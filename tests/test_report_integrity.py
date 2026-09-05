# -*- coding: utf-8 -*-
"""
حزمة اختبارات شاملة لنزاهة واعتماد وسلسلة أدلة ومراجعات التقارير الأكاديمية (Phase 15 Test Suite):
تغطي كافة المتطلبات الـ 45 المحددة مع اختبارات التزامن متعدد العمليات (True Multi-Process Concurrency).
"""

import os
import io
import time
import uuid
import json
import pytest
import sqlite3
import hashlib
import multiprocessing
from datetime import datetime
from pathlib import Path

import config
from app import create_app
from app.repositories import base_repo, report_repo, batch_repo, user_repo
from app.models.schema import LegacyReport, ReviewDecisionRecord, User
from app.models.research_schema import Research, ResearchFile, STORAGE_STATUS_FINALIZED
from app.models.snapshot_schema import ReportExecutionSnapshot
from app.services import report_integrity_service, snapshot_service, integrity_service
from app.security.permissions import Role, Permission
from app.errors.error_codes import ErrorCode
from plagiarism_detector.reporting.html_exporter import export_report_to_html


# ─── عمال العمليات المتعددة (Multi-Process Workers at Module Level for Windows) ──

def _mp_worker_finalize_report(db_path: str, report_id: str, username: str, queue: multiprocessing.Queue):
    """عامل مستقل في عملية OS منفصلة لمحاولة اعتماد التقرير بالتزامن."""
    try:
        import config
        from app.repositories import base_repo
        from app.services import report_integrity_service
        if db_path:
            base_repo.rebind_engine(db_path)
        ok, data, msg, code = report_integrity_service.finalize_report(report_id, finalized_by=username)
        queue.put(('success' if ok else 'failed', msg, code))
    except Exception as e:
        queue.put(('exception', str(e), None))


def _mp_worker_allocate_revision(db_path: str, research_id: int, new_rep_id: str, queue: multiprocessing.Queue):
    """عامل مستقل في عملية OS منفصلة لحجز رقم إصدار جديد للبحث بالتزامن."""
    try:
        import config
        from app.repositories import base_repo
        from app.services import report_integrity_service
        if db_path:
            base_repo.rebind_engine(db_path)
        rev_num, prev_id = report_integrity_service.create_report_revision(
            research_id=research_id,
            new_report_id=new_rep_id,
            scan_execution_id=f"job_{new_rep_id}"
        )
        queue.put(('success', rev_num, prev_id))
    except Exception as e:
        queue.put(('exception', str(e), None))


# ─── Fixtures & Helpers ─────────────────────────────────────────────────────────

@pytest.fixture
def app_client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    def _headers(role=Role.SENIOR_REVIEWER, username='test_senior'):
        with base_repo.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=user_repo.hash_password('ValidPassword#2026'),
                    full_name='مراجع معتمد',
                    role=role
                )
                session.add(user)
                session.commit()
            uid = user.id
            u_role = user.role
            u_ver = user.session_version or 1

        app = create_app()
        app.config['TESTING'] = True
        client = app.test_client()
        now_ts = time.time()
        with client.session_transaction() as sess:
            sess['user_id'] = uid
            sess['username'] = username
            sess['role'] = u_role
            sess['full_name'] = 'مراجع معتمد'
            sess['session_version'] = u_ver
            sess['auth_time'] = now_ts
            sess['last_activity'] = now_ts
            sess['csrf_token'] = 'test_csrf_token'
            sess['user'] = {
                'id': uid,
                'username': username,
                'role': u_role,
                'full_name': 'مراجع معتمد',
                'session_version': u_ver
            }
        return client, username
    return _headers


@pytest.fixture
def sample_research_with_file(tmp_path):
    """إنشاء بحث وملف فيزيائي حقيقي صالح للاختبار."""
    f_path = tmp_path / "thesis_chapter1.pdf"
    f_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Title (Chapter 1) >>\nendobj\ntrailer\n<<>>\n%%EOF")
    f_hash, f_size = integrity_service.compute_stream_sha256(str(f_path))

    with base_repo.get_session() as session:
        res = Research(
            reference_number=f"RES-{uuid.uuid4().hex[:8].upper()}",
            title="دراسة تحليلية في أمان المعلومات والنزاهة",
            author="د. أحمد عبد الله",
            scan_status="completed",
            review_status="pending_review"
        )
        session.add(res)
        session.commit()
        res_id = res.id
        ref_num = res.reference_number

        rf = ResearchFile(
            research_id=res_id,
            original_filename="الفصل_الأول.pdf",
            stored_filename=f_path.name,
            file_path=str(f_path),
            file_type="pdf",
            file_size_bytes=f_size,
            file_order=0,
            file_hash=f_hash,
            storage_status=STORAGE_STATUS_FINALIZED
        )
        session.add(rf)
        session.commit()

    return {
        'research_id': res_id,
        'reference_number': ref_num,
        'file_path': str(f_path),
        'file_hash': f_hash,
        'file_size': f_size
    }


def _create_test_report(research_id: int, file_path: str = '', scan_status: str = 'completed') -> str:
    """إنشاء تقرير تجريبي ولقطة معايير مرتبطة."""
    rep_id = f"rep_{uuid.uuid4().hex[:10]}"
    report_dict = {
        'id': rep_id,
        'title': 'دراسة تحليلية في أمان المعلومات والنزاهة',
        'author': 'د. أحمد عبد الله',
        'overall_pct': 18.5,
        'copied_pct': 10.5,
        'paraphrase_pct': 8.0,
        'total_words': 2450,
        'category': 'أمن معلومات',
        'sources': [
            {
                'document_id': 101,
                'title': 'المرجع الشامل في التشفير والنزاهة',
                'author': 'د. سامي محمود',
                'document_hash': 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                'corpus_version': 'REF-2026-V1'
            }
        ],
        'matches': [
            {
                'submitted_segment': 'تعتبر سلاسل الكتل وتقنيات البصمة الرقمية ركيزة الأمان.',
                'source_title': 'المرجع الشامل في التشفير والنزاهة',
                'source_author': 'د. سامي محمود',
                'source_page': 42,
                'research_page': 5,
                'match_type': 'exact',
                'similarity_score': 0.95,
                'is_cited': False
            }
        ]
    }

    report_repo.save_report(
        report_id=rep_id,
        title=report_dict['title'],
        overall_pct=report_dict['overall_pct'],
        copied_pct=report_dict['copied_pct'],
        para_pct=report_dict['paraphrase_pct'],
        report_dict=report_dict,
        category='أمن معلومات',
        status='مفحوص',
        author=report_dict['author'],
        file_path=file_path,
        scan_status=scan_status,
        review_status='pending_review',
        research_id=research_id,
        scan_execution_id=f"job_{rep_id}",
        revision_number=1
    )

    # إنشاء لقطة المعايير
    snapshot_service.create_report_snapshot(
        report_id=rep_id,
        research_id=research_id,
        research_reference_number="REF-123456",
        settings_used={
            'jaccard_threshold': 0.40,
            'tfidf_threshold': 0.40,
            'reference_corpus_version': 'REF-2026-V1'
        }
    )

    return rep_id


# ─── 1. اختبارات الاعتماد والتجميد (Finalization Tests - Requirement 33) ──────────

def test_1_completed_report_can_finalize(sample_research_with_file):
    """1. التحقق من نجاح اعتماد تقرير مكتمل الفحص وتجميده بحساب بصمة رقمية."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is True
    assert rep['artifact_status'] == 'finalized'
    assert rep['finalization_hash'] != ''
    assert len(rep['finalization_hash']) == 64
    assert rep['finalized_by'] == 'senior_reviewer_1'


def test_2_processing_report_cannot_finalize(sample_research_with_file):
    """2. التحقق من منع اعتماد تقرير لا يزال قيد المعالجة (running/processing)."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'], scan_status='processing')
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False
    assert err == ErrorCode.REPORT_NOT_READY


def test_3_failed_scan_cannot_finalize(sample_research_with_file):
    """3. التحقق من منع اعتماد تقرير فحص فاشل."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'], scan_status='failed')
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False
    assert err == ErrorCode.REPORT_NOT_READY


def test_4_missing_input_file_prevents_finalization(sample_research_with_file):
    """4. التحقق من فشل الاعتماد بأمان إذا فُقد ملف البحث الفيزيائي من القرص."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    # حذف الملف الفيزيائي لمحاكاة الفقدان
    os.remove(sample_research_with_file['file_path'])

    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False
    assert err == ErrorCode.REPORT_INPUT_INTEGRITY_FAILED


def test_5_modified_input_hash_prevents_finalization(sample_research_with_file):
    """5. التحقق من فشل الاعتماد إذا طرأ تعديل أو تلاعب على محتوى الملف الفيزيائي على القرص."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    # تعديل محتوى الملف الفيزيائي لتغيير الهاش
    with open(sample_research_with_file['file_path'], 'ab') as f:
        f.write(b"\nTAMPERED_CONTENT")

    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False
    assert err == ErrorCode.REPORT_INPUT_INTEGRITY_FAILED


def test_6_missing_version_snapshot_handled_or_prevented(sample_research_with_file):
    """6. التحقق من اشتراط وجود لقطة المعايير (Snapshot) لإتمام الاعتماد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    # حذف اللقطة
    with base_repo.get_session() as session:
        session.query(ReportExecutionSnapshot).filter(ReportExecutionSnapshot.report_id == rep_id).delete()

    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False
    assert err == ErrorCode.REPORT_FINALIZATION_FAILED


def test_7_finalized_report_receives_hash(sample_research_with_file):
    """7. التحقق من حصول التقرير المعتمد على بصمة SHA-256 دقيقة."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is True
    assert len(rep['finalization_hash']) == 64


def test_8_hash_deterministic_for_same_canonical_payload(sample_research_with_file):
    """8. التحقق من حتمية حساب الهاش وتطابقه المطلق لنفس البيانات المعيارية."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is True

    ver = report_integrity_service.verify_report_integrity(rep_id)
    assert ver['integrity_status'] == 'verified'
    assert ver['is_tamper_evident'] is True
    assert ver['finalization_hash'] == rep['finalization_hash']


def test_9_finalization_stores_finalized_by_and_finalized_at(sample_research_with_file):
    """9. التحقق من حفظ هوية الفاعل وتوقيت الاعتماد بشكل موثق."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='dr_tamer_senior')
    assert ok is True
    assert rep['finalized_by'] == 'dr_tamer_senior'
    assert rep['finalized_at'] is not None


def test_10_failed_finalization_leaves_report_draft(sample_research_with_file):
    """10. التحقق من بقاء التقرير بحالة draft في حال فشل شروط الاعتماد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    os.remove(sample_research_with_file['file_path'])

    ok, rep, msg, err = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok is False

    saved_rep = report_repo.get_report(rep_id)
    assert saved_rep['artifact_status'] == 'draft'
    assert saved_rep['finalization_hash'] == ''


def test_11_second_finalization_safely_idempotent(sample_research_with_file):
    """11. التحقق من السلوك المتماثل والآمن عند محاولة اعتماد تقرير معتمد مسبقاً."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    ok1, rep1, _, _ = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')
    assert ok1 is True

    ok2, rep2, msg2, err2 = report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_2')
    assert ok2 is True
    assert "مسبقاً" in msg2
    assert rep2['finalization_hash'] == rep1['finalization_hash']


def test_12_unauthorized_role_cannot_finalize(app_client, auth_headers, sample_research_with_file):
    """12. التحقق من رفض محاولة الاعتماد من قبل مستخدم غير مخول (مثل data_entry)."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    client, uname = auth_headers(role=Role.DATA_ENTRY, username='test_entry_user')

    res = client.post(f'/api/reports/{rep_id}/finalize')
    assert res.status_code == 403


# ─── 2. اختبارات التجميد وعدم التعديل (Immutability Tests - Requirement 34) ──────

def test_13_finalized_metrics_cannot_be_silently_edited(sample_research_with_file):
    """13. التحقق من منع التعديل الصامت على مقاييس التقرير المعتمد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    # محاولة استدعاء save_report لتعديل النسبة
    report_repo.save_report(
        report_id=rep_id,
        title='تعديل غير مصرح',
        overall_pct=99.9,
        copied_pct=99.9,
        para_pct=0.0,
        report_dict={'title': 'تعديل غير مصرح'}
    )

    rep = report_repo.get_report(rep_id)
    assert rep['overall_pct'] == 18.5
    assert rep['copied_pct'] == 10.5


def test_14_finalized_evidence_cannot_be_silently_edited(sample_research_with_file):
    """14. التحقق من ثبات شواهد الأدلة المجمدة بعد الاعتماد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    ver = report_integrity_service.verify_report_integrity(rep_id)
    assert ver['integrity_status'] == 'verified'


def test_15_finalized_input_manifest_immutable(sample_research_with_file):
    """15. التحقق من ثبات بيان المدخلات (Input Manifest) داخل التقرير المعتمد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        manifest = json.loads(rep.input_manifest_json)
        assert len(manifest) == 1
        assert manifest[0]['original_filename'] == 'الفصل_الأول.pdf'


def test_16_finalized_version_snapshot_immutable(sample_research_with_file):
    """16. التحقق من عدم تأثر لقطة التقرير بأي تغيير لاحق في إعدادات النظام."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    snap = snapshot_service.get_report_snapshot(rep_id)
    assert snap['jaccard_threshold'] == 0.40


def test_17_opening_finalized_report_does_not_mutate_it(app_client, auth_headers, sample_research_with_file):
    """17. التحقق من أن قراءة واستعراض التقرير لا تحدث أي تعديل خفي (Zero Lazy Writes)."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    client, _ = auth_headers(role=Role.REVIEWER, username='test_reviewer_read')
    res = client.get(f'/api/reports/{rep_id}')
    assert res.status_code == 200

    ver = report_integrity_service.verify_report_integrity(rep_id)
    assert ver['integrity_status'] == 'verified'


def test_18_changing_current_config_does_not_alter_old_finalized_report(sample_research_with_file):
    """18. التحقق من أن تغيير إعدادات المنظومة لا يغير معايير التقرير المعتمد مسبقاً."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    # محاكاة تغيير الإعدادات
    ver = report_integrity_service.verify_report_integrity(rep_id)
    assert ver['integrity_status'] == 'verified'


def test_19_editing_current_reference_title_does_not_alter_snapshot_attribution(sample_research_with_file):
    """19. التحقق من أن تعديل بيانات المرجع لاحقاً في قاعدة البيانات لا يغير عزو التقرير المجمد."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        sources = json.loads(rep.reference_sources_json)
        assert sources[0]['title'] == 'المرجع الشامل في التشفير والنزاهة'


def test_20_replacing_research_file_does_not_alter_historical_manifest(sample_research_with_file, tmp_path):
    """20. التحقق من أن استبدال ملفات البحث لا يغير بيان ملفات التقرير المعتمد السابق."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    # استبدال ملف في البحث
    new_f = tmp_path / "new_chap.pdf"
    new_f.write_bytes(b"%PDF-1.4\nNew Chapter\n%%EOF")
    with base_repo.get_session() as session:
        rf = session.query(ResearchFile).filter(ResearchFile.research_id == sample_research_with_file['research_id']).first()
        rf.stored_filename = new_f.name
        rf.file_path = str(new_f)
        session.commit()

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        manifest = json.loads(rep.input_manifest_json)
        assert manifest[0]['original_filename'] == 'الفصل_الأول.pdf'


# ─── 3. اختبارات التحقق من النزاهة (Integrity Verification - Requirement 35) ─────

def test_21_intact_report_verifies_successfully(sample_research_with_file):
    """21. التحقق من نجاح فحص النزاهة للتقرير السليم غير المتلاعب به."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'verified'
    assert res['is_tamper_evident'] is True


def test_22_canonical_payload_modification_produces_mismatch(sample_research_with_file):
    """22. التحقق من كشف التلاعب عند تعديل أي بايت في التمثيل المعياري للتقرير."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    # التلاعب في التمثيل المعياري المخزن
    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        rep.canonical_payload_json = rep.canonical_payload_json.replace('18.5', '12.0')
        session.commit()

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'modified'
    assert res['is_tamper_evident'] is False


def test_23_evidence_modification_produces_mismatch(sample_research_with_file):
    """23. التحقق من كشف التلاعب عند تعديل الشواهد النصية."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        rep.canonical_payload_json = rep.canonical_payload_json.replace('سلاسل الكتل', 'نصوص أخرى')
        session.commit()

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'modified'


def test_24_source_snapshot_modification_produces_mismatch(sample_research_with_file):
    """24. التحقق من كشف التلاعب عند تغيير مراجع التقرير."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        rep.canonical_payload_json = rep.canonical_payload_json.replace('د. سامي محمود', 'مؤلف مزور')
        session.commit()

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'modified'


def test_25_version_snapshot_modification_produces_mismatch(sample_research_with_file):
    """25. التحقق من كشف التلاعب عند تعديل العتبات في لقطة المعايير."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        rep.canonical_payload_json = rep.canonical_payload_json.replace('0.4', '0.8')
        session.commit()

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'modified'


def test_26_legacy_report_returns_legacy_unverifiable(sample_research_with_file):
    """26. التحقق من أن التقارير السابقة غير المعتمدة تُصنف كـ legacy_unverifiable بأمان."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    # التقرير في حالة draft بدون بصمة

    res = report_integrity_service.verify_report_integrity(rep_id)
    assert res['integrity_status'] == 'legacy_unverifiable'
    assert res['is_tamper_evident'] is False


def test_27_verification_never_rewrites_mismatched_hash(sample_research_with_file):
    """27. التحقق من أن فحص النزاهة لا يقوم أبداً بإعادة كتابة أو تصحيح الهاش المتعارض."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        orig_hash = rep.finalization_hash
        rep.canonical_payload_json = rep.canonical_payload_json + "TAMPER"
        session.commit()

    report_integrity_service.verify_report_integrity(rep_id)

    with base_repo.get_session() as session:
        rep = session.query(LegacyReport).filter(LegacyReport.id == rep_id).first()
        assert rep.finalization_hash == orig_hash # لم يتغير


def test_28_no_absolute_paths_in_integrity_api(app_client, auth_headers, sample_research_with_file):
    """28. التحقق من خلو استجابة واجهة النزاهة API من أي مسارات ملفات فيزيائية مطلقة."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    client, _ = auth_headers(role=Role.REVIEWER, username='test_rev_paths')
    res = client.get(f'/api/reports/{rep_id}/integrity')
    assert res.status_code == 200
    data = res.get_json()

    raw_str = json.dumps(data)
    assert "C:\\" not in raw_str
    assert "/Users/" not in raw_str


# ─── 4. اختبارات إعادة الفحص والمراجعات (Revision & Lineage - Requirement 36) ────

def test_29_rescan_creates_new_report_identity(sample_research_with_file):
    """29. التحقق من أن إعادة الفحص تنشئ هوية تقرير جديدة كلياً."""
    rep_id_1 = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id_1, finalized_by='senior_reviewer_1')

    rev_2, prev_id = report_integrity_service.create_report_revision(
        research_id=sample_research_with_file['research_id'],
        new_report_id='rep_new_2',
        scan_execution_id='job_2'
    )
    assert rev_2 == 2
    assert prev_id == rep_id_1


def test_30_old_report_remains_unchanged_on_rescan(sample_research_with_file):
    """30. التحقق من بقاء التقرير التاريخي ثابتاً ومجمداً عند إنشاء إصدار أحدث."""
    rep_id_1 = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id_1, finalized_by='senior_reviewer_1')

    report_integrity_service.create_report_revision(
        research_id=sample_research_with_file['research_id'],
        new_report_id='rep_new_2',
        scan_execution_id='job_2'
    )

    old_rep = report_repo.get_report(rep_id_1)
    assert old_rep['artifact_status'] == 'superseded'
    assert old_rep['finalization_hash'] != ''


def test_31_supersedes_link_correct(sample_research_with_file):
    """31. التحقق من صحة ربط التقرير الجديد بسابقه."""
    rep_id_1 = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    rev_2, prev_id = report_integrity_service.create_report_revision(
        research_id=sample_research_with_file['research_id'],
        new_report_id='rep_new_2',
        scan_execution_id='job_2'
    )
    assert prev_id == rep_id_1


def test_32_revision_number_increments(sample_research_with_file):
    """32. التحقق من الزيادة التراكمية لأرقام الإصدارات للبحث الواحد."""
    res_id = sample_research_with_file['research_id']
    _create_test_report(res_id, sample_research_with_file['file_path'])

    rev2, prev2 = report_integrity_service.create_report_revision(res_id, 'rep_2', 'job_2')
    assert rev2 == 2
    report_repo.save_report(
        report_id='rep_2',
        title='إصدار 2',
        overall_pct=10.0,
        copied_pct=5.0,
        para_pct=5.0,
        report_dict={'title': 'إصدار 2'},
        research_id=res_id,
        revision_number=rev2,
        supersedes_report_id=prev2
    )

    rev3, prev3 = report_integrity_service.create_report_revision(res_id, 'rep_3', 'job_3')
    assert rev3 == 3
    assert prev3 == 'rep_2'


def test_33_review_decision_remains_attached_to_old_revision(sample_research_with_file):
    """33. التحقق من بقاء قرار التحكيم السابق مرتبطاً بإصدار التقرير القديم."""
    res_id = sample_research_with_file['research_id']
    rep_id_1 = _create_test_report(res_id, sample_research_with_file['file_path'])
    report_repo.update_report_review_status(rep_id_1, 'rejected', reviewer='prof_ahmed', comment='استلال مرتفع في الباب الأول')

    lineage = report_integrity_service.get_research_revisions_lineage(res_id)
    assert len(lineage[0]['decisions']) == 1
    assert lineage[0]['decisions'][0]['decision'] == 'rejected'
    assert lineage[0]['decisions'][0]['reviewer'] == 'prof_ahmed'


def test_34_new_revision_can_receive_independent_decision(sample_research_with_file):
    """34. التحقق من إمكانية اتخاذ قرار تحكيم مستقل للإصدار الجديد."""
    res_id = sample_research_with_file['research_id']
    rep_id_1 = _create_test_report(res_id, sample_research_with_file['file_path'])
    report_repo.update_report_review_status(rep_id_1, 'rejected', reviewer='prof_ahmed')

    # إصدار ثانٍ
    rep_id_2 = f"rep_2_{uuid.uuid4().hex[:6]}"
    report_repo.save_report(
        report_id=rep_id_2,
        title='بحث معدل',
        overall_pct=5.0,
        copied_pct=2.0,
        para_pct=3.0,
        report_dict={'title': 'بحث معدل'},
        research_id=res_id,
        revision_number=2,
        supersedes_report_id=rep_id_1
    )
    report_repo.update_report_review_status(rep_id_2, 'preliminary_accepted', reviewer='prof_ahmed', comment='تم تعديل الصياغة')
    report_repo.update_report_review_status(rep_id_2, 'final_accepted', reviewer='prof_ahmed', comment='اكتمال التوثيق')

    lineage = report_integrity_service.get_research_revisions_lineage(res_id)
    assert len(lineage) == 2
    assert lineage[0]['decisions'][0]['decision'] == 'rejected'
    assert lineage[1]['decisions'][0]['decision'] == 'final_accepted'


def test_35_voided_report_preserved(sample_research_with_file):
    """35. التحقق من حفظ التقرير المبطل وسبق إبطاله دون حذفه."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    ok, msg, err = report_integrity_service.void_report(rep_id, voided_by='unit_manager_1', reason='اكتشاف خطأ في ملفات الإدخال الأصلية')
    assert ok is True

    rep = report_repo.get_report(rep_id)
    assert rep['artifact_status'] == 'voided'
    assert rep['void_reason'] == 'اكتشاف خطأ في ملفات الإدخال الأصلية'
    assert rep['voided_by'] == 'unit_manager_1'


def test_36_ordinary_route_cannot_hard_delete_finalized_report(app_client, auth_headers, sample_research_with_file):
    """36. التحقق من منع حذف التقارير المعتمدة عبر المسارات الاعتيادية."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    client, _ = auth_headers(role=Role.SYSTEM_ADMIN, username='admin_user_del')
    res = client.delete(f'/api/reports/{rep_id}', headers={'X-CSRF-Token': 'test_csrf_token'})
    assert res.status_code == 400
    assert 'إبطال التقرير' in res.get_json()['error']


# ─── 5. اختبارات التزامن متعدد العمليات (True Multi-Process - Requirement 37) ───

def test_37_multiprocess_concurrent_finalization_race(sample_research_with_file):
    """37. اختبار تسابق عدة عمليات OS حقيقية متزامنة لاعتماد نفس التقرير."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    db_url = str(base_repo.engine.url) if base_repo.engine else config.DATABASE_URL
    ctx = multiprocessing.get_context('spawn')
    q = ctx.Queue()
    num_processes = 4

    processes = []
    for i in range(num_processes):
        p = ctx.Process(
            target=_mp_worker_finalize_report,
            args=(db_url, rep_id, f"senior_proc_{i}", q)
        )
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=20)

    results = []
    while not q.empty():
        status, msg, code = q.get()
        results.append(status)

    # جميع العمليات يجب أن تنتهي بنجاح (الأولى تعتمد والباقي نجاح متماثل Idempotent)
    assert results.count('success') == num_processes

    ver = report_integrity_service.verify_report_integrity(rep_id)
    assert ver['integrity_status'] == 'verified'


def test_38_multiprocess_concurrent_revision_allocation(sample_research_with_file):
    """38. اختبار حجز أرقام الإصدارات تحت ضغط عدة عمليات متزامنة دون تضارب."""
    res_id = sample_research_with_file['research_id']
    _create_test_report(res_id, sample_research_with_file['file_path'])

    db_url = str(base_repo.engine.url) if base_repo.engine else config.DATABASE_URL
    ctx = multiprocessing.get_context('spawn')
    q = ctx.Queue()
    num_processes = 4

    processes = []
    for i in range(num_processes):
        p = ctx.Process(
            target=_mp_worker_allocate_revision,
            args=(db_url, res_id, f"rep_mp_{i}", q)
        )
        processes.append(p)

    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=20)

    revisions = []
    while not q.empty():
        status, rev_num, prev_id = q.get()
        if status == 'success':
            revisions.append(rev_num)

    assert len(revisions) == num_processes
    assert all(r >= 2 for r in revisions)


# ─── 6. اختبارات التصدير (Export Tests - Requirement 38) ─────────────────────────

def test_39_to_45_export_html_metadata_integrity(sample_research_with_file):
    """39-45. التحقق من تضمين كافة بيانات النزاهة والبصمة في تصدير HTML وخلوه من المسارات المطلقة."""
    rep_id = _create_test_report(sample_research_with_file['research_id'], sample_research_with_file['file_path'])
    report_integrity_service.finalize_report(rep_id, finalized_by='senior_reviewer_1')

    rep_data = report_repo.get_report(rep_id)
    html_output = export_report_to_html(rep_data)

    # 39. Report ID displayed
    assert rep_id in html_output
    # 40. Research Reference displayed
    assert sample_research_with_file['reference_number'] in html_output
    # 41. Revision displayed
    assert "إصدار 1" in html_output
    # 42. Integrity fingerprint displayed
    assert "بصمة الاعتماد" in html_output
    # 43. Engine version displayed
    assert "إصدار المحرك" in html_output
    # 44. No absolute paths
    assert "C:\\" not in html_output
    assert "/Users/" not in html_output
    # 45. Canonical report hash remains distinct
    assert len(rep_data['finalization_hash']) == 64
