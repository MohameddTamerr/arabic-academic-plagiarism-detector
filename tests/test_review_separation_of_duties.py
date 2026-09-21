"""
Tests for Institutional Separation of Duties and Review Workflow:
- EMPLOYEE role 403 on review actions
- REVIEWER role allowed for preliminary/reject, 403 on final accept
- SENIOR_REVIEWER allowed for all review actions
- Self-Review Protection (Reviewer cannot review self-submitted research)
- Immutable ReviewDecisionRecord creation
"""
import json
import uuid
import pytest
from app import create_app
from app.models.schema import LegacyReport, ReviewDecisionRecord, User
from app.repositories.base_repo import get_session as get_db_session


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_separation_of_duties_and_self_review(client, app_instance):
    """Test RBAC enforcement and self-review protection."""
    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    with get_db_session() as session:
        # Create users in DB
        u_submitter = User(username=f"rev_sub_{uuid.uuid4().hex[:4]}", password_hash="h", full_name="Reviewer Submitter", role="reviewer", is_active=1)
        u_employee = User(username=f"emp_test_{uuid.uuid4().hex[:4]}", password_hash="h", full_name="Employee User", role="employee", is_active=1)
        u_independent_rev = User(username=f"rev_ind_{uuid.uuid4().hex[:4]}", password_hash="h", full_name="Independent Reviewer", role="reviewer", is_active=1)
        u_senior_rev = User(username=f"srev_test_{uuid.uuid4().hex[:4]}", password_hash="h", full_name="Senior Reviewer", role="senior_reviewer", is_active=1)
        session.add_all([u_submitter, u_employee, u_independent_rev, u_senior_rev])
        session.commit()

        sub_id = u_submitter.id
        sub_name = u_submitter.username
        emp_id = u_employee.id
        emp_name = u_employee.username
        ind_rev_id = u_independent_rev.id
        ind_rev_name = u_independent_rev.username
        srev_id = u_senior_rev.id
        srev_name = u_senior_rev.username

        # Create a report submitted by u_submitter
        rep_data = {
            'segments': [{'text': 'محتوى أصلي محفوظ لاختبار فصل المهام ومنع مراجعة المستخدم لبحثه'}],
            'clean_words_count': 2000,
            'total_words': 2000,
            'copied_words': 100,
            'paraphrase_words': 0,
            'problematic_pct': 5.0,
            'overall_pct': 5.0
        }
        rep = LegacyReport(
            id=report_id,
            title='بحث تجريبي للتدقيق المؤسسي',
            author='الباحث الخارجي',
            submitted_by=sub_name,
            submitted_by_user_id=sub_id,
            status='محفوظ',
            scan_status='completed',
            review_status='pending_review',
            overall_pct=5.0,
            copied_pct=5.0,
            para_pct=0.0,
            report_json=json.dumps(rep_data)
        )
        session.add(rep)
        session.commit()

    # 1. EMPLOYEE role tries to do preliminary accept -> 403 Forbidden
    with client.session_transaction() as sess:
        sess['user_id'] = emp_id
        sess['role'] = 'employee'
        sess['username'] = emp_name

    res = client.post(f'/api/reports/{report_id}/initial_accept')
    assert res.status_code == 403

    res = client.post(f'/api/reports/{report_id}/reject', json={'reason': 'Invalid'})
    assert res.status_code == 403

    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 403

    # 2. SELF-REVIEW PROTECTION: Submitter tries to review own paper -> 403 Forbidden
    with client.session_transaction() as sess:
        sess['user_id'] = sub_id
        sess['role'] = 'reviewer'
        sess['username'] = sub_name

    res = client.post(f'/api/reports/{report_id}/initial_accept')
    assert res.status_code == 403
    assert 'فصل المهام' in (res.get_json().get('error') or '')

    # 3. INDEPENDENT REVIEWER reviews paper -> 200 Success
    with client.session_transaction() as sess:
        sess['user_id'] = ind_rev_id
        sess['role'] = 'reviewer'
        sess['username'] = ind_rev_name

    res = client.post(f'/api/reports/{report_id}/initial_accept', json={'decision_notes': 'استوفى المعايير الأولية'})
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 4. Standard REVIEWER tries to do FINAL accept -> 403 Forbidden (Only Senior Reviewer / Admin)
    res = client.post(f'/api/reports/{report_id}/final_accept')
    assert res.status_code == 403

    # 5. SENIOR REVIEWER does FINAL accept -> 200 Success
    with client.session_transaction() as sess:
        sess['user_id'] = srev_id
        sess['role'] = 'senior_reviewer'
        sess['username'] = srev_name

    res = client.post(f'/api/reports/{report_id}/final_accept', json={'decision_notes': 'معتمد نهائياً'})
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 6. Verify ReviewDecisionRecord in DB
    with get_db_session() as session:
        records = session.query(ReviewDecisionRecord).filter_by(report_id=report_id).all()
        assert len(records) >= 2
        decision_types = [r.decision for r in records]
        assert 'preliminary_accepted' in decision_types
        assert 'final_accepted' in decision_types
