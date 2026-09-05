# -*- coding: utf-8 -*-
"""
اختبارات العقود المشتركة لقواعد البيانات (Cross-Backend Contract Tests):
- التحقق من توافق العمليات الأساسية (CRUD، المعاملات، التراجع Rollback).
- التحقق من التوليد الذري للأرقام المرجعية المنضبطة.
- التحقق من دورة حياة التقارير وحفظ بصمات النزاهة.
"""

import pytest
from app.repositories import base_repo
from app.models.research_schema import Research, ReferenceSequence
from app.models.schema import LegacyReport, User
from app.services import reference_service


def test_atomic_sequence_generation():
    """التحقق من التوليد التسلسلي الذري والمنضبط للأرقام المرجعية."""
    ref1 = reference_service.get_next_research_reference(year=2026, prefix='RES')
    ref2 = reference_service.get_next_research_reference(year=2026, prefix='RES')
    ref3 = reference_service.get_next_research_reference(year=2026, prefix='RES')

    assert ref1.startswith("RES-2026-")
    assert ref2.startswith("RES-2026-")
    assert ref3.startswith("RES-2026-")

    # التحقق من الزيادة التتابعية
    seq1 = int(ref1.split('-')[-1])
    seq2 = int(ref2.split('-')[-1])
    seq3 = int(ref3.split('-')[-1])

    assert seq2 == seq1 + 1
    assert seq3 == seq2 + 1


def test_transaction_rollback_preserves_database_state():
    """التحقق من أن استثناءات المعاملات تتراجع بشكل حتمي دون ترك سجلات جزئية."""
    initial_count = 0
    with base_repo.get_session() as session:
        initial_count = session.query(User).count()

    try:
        with base_repo.get_session() as session:
            u = User(username="temp_user_rollback", password_hash="hashed_pw", full_name="Test User", role="reviewer")
            session.add(u)
            session.flush()
            # إطلاق استثناء متعمد لاختبار التراجع
            raise ValueError("Deliberate failure for rollback test")
    except ValueError:
        pass

    with base_repo.get_session() as session:
        final_count = session.query(User).count()
        assert final_count == initial_count
        assert session.query(User).filter_by(username="temp_user_rollback").first() is None


def test_report_lifecycle_persistence():
    """التحقق من حفظ واسترجاع حالات التقارير وبصمة النزاهة بدقة."""
    import uuid
    rep_id = str(uuid.uuid4())
    with base_repo.get_session() as session:
        rep = LegacyReport(
            id=rep_id,
            title="بحث تجريبي",
            author="الباحث التجريبي",
            overall_pct=15.5,
            copied_pct=10.0,
            para_pct=5.5,
            status='finalized',
            scan_status='completed',
            review_status='approved',
            report_json='{}',
            artifact_status='finalized',
            finalization_hash='a'*64
        )
        session.add(rep)
        session.flush()

    with base_repo.get_session() as session:
        saved = session.query(LegacyReport).filter_by(id=rep_id).first()
        assert saved is not None
        assert saved.overall_pct == 15.5
        assert saved.status == 'finalized'
        assert saved.finalization_hash == 'a'*64



