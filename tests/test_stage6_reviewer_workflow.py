# -*- coding: utf-8 -*-
"""Isolated Stage 6 regression tests; no production database is touched."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.reviewer_workflow_schema import create_reviewer_workflow_schema_for_isolated_testing
from app.services.reviewer_workflow_service import record_decision, list_decisions, ReviewWorkflowError
from plagiarism_detector.reporting.reviewer_evidence import (
    build_evidence_catalog, calculate_reviewer_adjusted_coverage, evidence_version,
)


def _report():
    return {
        'id': 'stage6-fixture', 'revision_number': 1,
        'scoring_version': 'stage2_aligned_token_coverage_v1',
        'coverage_denominator_tokens': 10, 'overall_pct': 50.0,
        'raw_lexical_similarity_pct': 50.0,
        'segments': [{
            'text': 'النص العربي المطابق هنا', 'page_number': 2,
            'matched_token_indexes': [0, 1, 2, 3, 4],
            'alignment_evidence': [
                {'source_id': 11, 'source_reference_id': 'ref-a', 'source_title': 'مصدر ألف',
                 'source_page': 7, 'source_segment_number': 1,
                 'matched_suspicious_token_indexes': [0, 1, 2],
                 'spans': [{'suspicious_start': 0, 'suspicious_end': 8, 'source_start': 0, 'source_end': 8}]},
                {'source_id': 12, 'source_reference_id': 'ref-b', 'source_title': 'مصدر باء',
                 'source_page': 8, 'source_segment_number': 3,
                 'matched_suspicious_token_indexes': [2, 3, 4],
                 'spans': [{'suspicious_start': 5, 'suspicious_end': 15, 'source_start': 3, 'source_end': 13}]},
            ],
            'semantic_candidate_evidence': [{'source_id': 99, 'source_title': 'مرشح دلالي', 'score': .91}],
            'citation_links': [], 'citation_linkage_status': 'NO_CITATION',
            'source_verification_status': 'NOT_APPLICABLE',
        }],
    }


def _isolated_session(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'stage6_review_test.db').as_posix()}")
    create_reviewer_workflow_schema_for_isolated_testing(engine)
    return sessionmaker(bind=engine)(), engine


def test_multisource_catalog_and_unique_exclusion_coverage():
    report = _report()
    catalog = build_evidence_catalog(report)
    lexical = [item for item in catalog if item['kind'] == 'lexical']
    assert len(lexical) == 2
    assert len({item['evidence_id'] for item in catalog}) == 3
    assert catalog[-1]['matched_token_indexes'] == []  # semantic evidence is non-counting
    decisions = [
        {'id': 'a', 'evidence_id': lexical[0]['evidence_id'], 'evidence_version': evidence_version(report),
         'decision_type': 'EXCLUDED_WITH_JUSTIFICATION', 'is_current': True},
        {'id': 'b', 'evidence_id': lexical[1]['evidence_id'], 'evidence_version': evidence_version(report),
         'decision_type': 'EXCLUDED_WITH_JUSTIFICATION', 'is_current': True},
    ]
    result = calculate_reviewer_adjusted_coverage(report, decisions)
    assert result['raw_coverage_tokens'] == 5
    assert result['excluded_token_coverage'] == 5  # token 2 was not counted twice
    assert result['reviewer_adjusted_coverage_tokens'] == 0
    assert result['reviewer_adjusted_similarity_pct'] == 0.0
    assert report['overall_pct'] == 50.0


def test_stale_and_semantic_decisions_do_not_change_coverage():
    report = _report()
    semantic = next(item for item in build_evidence_catalog(report) if item['kind'] == 'semantic_candidate')
    result = calculate_reviewer_adjusted_coverage(report, [{
        'id': 'old', 'evidence_id': semantic['evidence_id'], 'evidence_version': 'obsolete',
        'decision_type': 'EXCLUDED_WITH_JUSTIFICATION', 'is_current': True,
    }])
    assert result['excluded_token_coverage'] == 0
    assert result['reviewer_adjusted_coverage_tokens'] == 5
    assert result['stale_decision_ids'] == ['old']


def test_append_only_decisions_idempotency_and_concurrent_revision_protection(tmp_path):
    report = _report(); evidence = build_evidence_catalog(report)[0]
    session, engine = _isolated_session(tmp_path)
    actor = {'id': 4, 'username': 'reviewer-a', 'role': 'reviewer'}
    first = record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
        evidence_version=evidence_version(report), actor=actor, decision_type='ACCEPTED', justification='مراجعة',
        idempotency_key='request-one', expected_previous_decision_id=None)
    session.commit()
    duplicate = record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
        evidence_version=evidence_version(report), actor=actor, decision_type='ACCEPTED', justification='مراجعة',
        idempotency_key='request-one', expected_previous_decision_id=None)
    assert duplicate['id'] == first['id']
    with pytest.raises(ReviewWorkflowError, match='STALE_DECISION_CONFLICT'):
        record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
            evidence_version=evidence_version(report), actor=actor, decision_type='NEEDS_REVIEW', justification='',
            idempotency_key='request-two', expected_previous_decision_id=None)
    with pytest.raises(ReviewWorkflowError, match='OTHER_REVIEWER_DECISION_PROTECTED'):
        record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
            evidence_version=evidence_version(report), actor={'id': 5, 'username': 'reviewer-b', 'role': 'reviewer'},
            decision_type='REJECTED', justification='سبب', idempotency_key='request-three',
            expected_previous_decision_id=first['id'])
    revised = record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
        evidence_version=evidence_version(report), actor={'id': 9, 'username': 'senior', 'role': 'senior_reviewer'},
        decision_type='EXCLUDED_WITH_JUSTIFICATION', justification='مرجع مكرر', idempotency_key='request-four',
        expected_previous_decision_id=first['id'], allow_other_reviewer_revision=True)
    session.commit()
    history = list_decisions(session, report['id'])
    assert len(history) == 2 and not history[0]['is_current'] and history[1]['is_current']
    assert revised['previous_decision_id'] == first['id']
    session.close(); engine.dispose()


def test_exclusion_requires_justification(tmp_path):
    report = _report(); evidence = build_evidence_catalog(report)[0]
    session, engine = _isolated_session(tmp_path)
    with pytest.raises(ReviewWorkflowError, match='EXCLUSION_JUSTIFICATION_REQUIRED'):
        record_decision(session, report_id=report['id'], evidence_id=evidence['evidence_id'],
            evidence_version=evidence_version(report), actor={'id': 4},
            decision_type='EXCLUDED_WITH_JUSTIFICATION', justification='', idempotency_key='no-reason',
            expected_previous_decision_id=None)
    session.close(); engine.dispose()


def test_isolated_reviewer_schema_migration_rollback(tmp_path):
    """The opt-in schema can be created and removed outside production metadata."""
    from sqlalchemy import inspect
    from app.reviewer_workflow_schema import ReviewerWorkflowBase
    engine = create_engine(f"sqlite:///{(tmp_path / 'stage6_rollback.db').as_posix()}")
    create_reviewer_workflow_schema_for_isolated_testing(engine)
    assert 'evidence_review_decisions' in inspect(engine).get_table_names()
    ReviewerWorkflowBase.metadata.drop_all(bind=engine)
    assert 'evidence_review_decisions' not in inspect(engine).get_table_names()
    engine.dispose()


def test_authenticated_stage6_route_requires_csrf_and_persists_in_isolated_app(monkeypatch):
    """Staging-style route exercise: auth, CSRF, schema, audit and exclusion."""
    import config
    from app import create_app
    from app.repositories import report_repo, base_repo
    from app.reviewer_workflow_schema import create_reviewer_workflow_schema_for_isolated_testing
    from app.models.audit_schema import AuditLog

    monkeypatch.setitem(config.DEFAULT_SETTINGS, 'enable_reviewer_evidence_workflow', True)
    create_reviewer_workflow_schema_for_isolated_testing(base_repo.engine)
    report = _report()
    report_repo.save_report('stage6-route', 'تقرير مرحلي', 50, 50, 0, report, author='باحث')
    app = create_app(); app.config.update(TESTING=True, ENFORCE_CSRF_IN_TESTS=True)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess.update({'user_id': 900, 'username': 'senior-stage', 'role': 'senior_reviewer'})
        evidence_response = client.get('/api/reports/stage6-route/reviewer-evidence')
        assert evidence_response.status_code == 200
        evidence = evidence_response.get_json()['evidence'][0]
        denied = client.post(
            f"/api/reports/stage6-route/reviewer-evidence/{evidence['evidence_id']}/decision",
            json={'decision_type': 'EXCLUDED_WITH_JUSTIFICATION', 'evidence_version': evidence['evidence_version'],
                  'idempotency_key': 'csrf-denied', 'justification': 'مكرر'},
        )
        assert denied.status_code == 403
        token = client.get('/api/auth/csrf-token').get_json()['csrf_token']
        created = client.post(
            f"/api/reports/stage6-route/reviewer-evidence/{evidence['evidence_id']}/decision",
            headers={'X-CSRF-Token': token},
            json={'decision_type': 'EXCLUDED_WITH_JUSTIFICATION', 'evidence_version': evidence['evidence_version'],
                  'idempotency_key': 'csrf-accepted', 'justification': 'مكرر'},
        )
        assert created.status_code == 201
    with base_repo.get_session() as session:
        assert session.query(AuditLog).filter(AuditLog.action == 'review.evidence_decision_recorded').count() >= 1
