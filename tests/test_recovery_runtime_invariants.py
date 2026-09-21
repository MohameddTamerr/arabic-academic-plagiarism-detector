"""Login/restart and internal PDF gates; never use deployment credentials/data."""
import uuid
import fitz
from app import create_app
from app.repositories import user_repo, base_repo, report_repo
from app.models.schema import User, SystemSecurityState


def test_existing_sysadmin_survives_restart_login_and_admin_operation():
    name = 'restart_admin_' + uuid.uuid4().hex
    password = 'Isolated#Admin2026Secure'
    with base_repo.get_session() as db:
        admin = User(username=name, password_hash=user_repo.hash_password(password),
                     full_name='Restart Admin', role='system_admin', is_active=1,
                     session_version=1, must_change_password=0, must_enroll_recovery=0)
        db.add(admin); db.flush(); uid = admin.id
        state = db.query(SystemSecurityState).filter_by(key='bootstrap_completed').first()
        if state: state.value = '1'
        else: db.add(SystemSecurityState(key='bootstrap_completed', value='1'))
    for _ in range(2):
        app = create_app(); app.config.update(TESTING=True, STRICT_AUTH=True)
        client = app.test_client()
        response = client.post('/api/auth/login', json={'username': name, 'password': password})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['user']['role'] == 'system_admin'
        assert client.get('/api/auth/me').get_json()['user']['role'] == 'system_admin'
        with client.session_transaction() as session:
            assert session['role'] == 'system_admin'
        assert client.get('/').status_code == 200
        assert client.get('/api/users?q=' + name).get_json()['users'][0]['role'] == 'system_admin'
        assert client.get('/api/papers').status_code == 200
        assert not user_repo.is_initial_admin_allowed()
        employee = 'restart_employee_' + uuid.uuid4().hex
        operation = client.post('/api/users', json={'username': employee, 'full_name': 'Test Employee',
                                                  'password': 'Temporary#2026', 'role': 'employee'})
        assert operation.status_code == 201
        with base_repo.get_session() as db:
            assert db.get(User, uid).role == 'system_admin'
            assert db.get(User, uid).session_version == 1


def test_internal_pdf_evidence_navigation_and_authorization(tmp_path):
    path = tmp_path / 'submitted.pdf'
    with fitz.open() as doc:
        doc.new_page(); doc.new_page(); doc.save(path)
    rid = 'pdf_' + uuid.uuid4().hex
    report_repo.save_report(report_id=rid, title='PDF Evidence', overall_pct=0, copied_pct=0,
                           para_pct=0, file_path=str(path), report_dict={'file_path': str(path), 'segments': []})
    app = create_app(); app.config.update(TESTING=True, STRICT_AUTH=True)
    client = app.test_client()
    assert client.get(f'/api/pdf/report/{rid}/info').status_code == 401
    with client.session_transaction() as session:
        session.update(user_id=9999999, username='isolated_pdf_employee', role='employee')
    info = client.get(f'/api/pdf/report/{rid}/info')
    assert info.status_code == 200 and info.get_json()['page_count'] == 2
    assert info.get_json()['coordinates_available'] is False
    page = client.get(f'/api/pdf/report/{rid}/page?page=2')
    assert page.status_code == 200 and page.data.startswith(b'\x89PNG')
    assert client.get(f'/api/pdf/report/{rid}/page?page=3').status_code == 400
    for method, route in [('get','/api/users'), ('get','/api/admin/audit_logs'), ('get','/api/settings'),
                          ('post',f'/api/reports/{rid}/final_accept'), ('post',f'/api/reports/{rid}/reject'),
                          ('post','/api/papers')]:
        assert getattr(client,method)(route).status_code == 403, route


def test_final_acceptance_commits_corpus_and_decision_atomically(monkeypatch):
    from app.services import corpus_governance_service
    from app.models.schema import Document
    rid = 'accept_' + uuid.uuid4().hex
    report_repo.save_report(report_id=rid, title='Acceptance Evidence', overall_pct=0,
                           copied_pct=0, para_pct=0,
                           report_dict={'segments': [{'text': 'محتوى أكاديمي أصلي محفوظ للقبول النهائي ' + rid}]})
    app = create_app(); app.config.update(TESTING=True, STRICT_AUTH=True)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=9999998, username='isolated_accepting_admin', role='system_admin')
    original = corpus_governance_service.add_reference_document
    monkeypatch.setattr(corpus_governance_service, 'add_reference_document', lambda **kwargs: {'success':False, 'error':'Safe mocked insertion failure'})
    assert client.post(f'/api/reports/{rid}/final_accept').status_code == 400
    assert report_repo.get_report(rid)['review_status'] == 'pending_review'
    monkeypatch.setattr(corpus_governance_service, 'add_reference_document', original)
    response = client.post(f'/api/reports/{rid}/final_accept')
    assert response.status_code == 200, response.get_json()
    assert report_repo.get_report(rid)['review_status'] == 'final_accepted'
    import json
    with base_repo.get_session() as db:
        reference = db.get(Document, response.get_json()['paper_id'])
        provenance = json.loads(reference.notes)
        assert provenance['report_id'] == rid
        assert provenance['approving_admin'] == 'isolated_accepting_admin'
        assert reference.active_from_version


def test_self_match_exclusion_uses_provenance_not_file_hash():
    import json
    from app.models.schema import Document
    from app.services.self_match_service import reference_ids_for_work
    token = uuid.uuid4().hex
    with base_repo.get_session() as db:
        own = Document(title='Own ' + token, notes=json.dumps({'research_id': 901234, 'thesis_id': 901235}))
        other = Document(title='Other ' + token, notes=json.dumps({'research_id': 901236}))
        db.add_all([own,other]); db.flush(); own_id,other_id = own.id,other.id
    assert reference_ids_for_work(research_id=901234) == {own_id}
    assert reference_ids_for_work(thesis_id=901235) == {own_id}
    assert other_id not in reference_ids_for_work(research_id=901234)
    assert reference_ids_for_work() == set()


def test_multifile_acceptance_late_failure_rolls_back_every_reference(tmp_path, monkeypatch):
    from app.repositories import batch_repo
    from app.services import final_acceptance_service, corpus_governance_service
    from app.models.schema import Document, ReviewDecisionRecord
    from app.models.snapshot_schema import ReferenceCorpusVersion
    rid='rollback_'+uuid.uuid4().hex
    report_repo.save_report(report_id=rid,title=rid,overall_pct=0,copied_pct=0,para_pct=0,
                           report_dict={'research_id': 901237})
    first=tmp_path/'first.txt'; second=tmp_path/'second.txt'
    first.write_text('هذا محتوى أكاديمي تجريبي أصلي '+rid,encoding='utf-8')
    second.write_text('محتوى الجزء الثاني المختلف '+rid,encoding='utf-8')
    monkeypatch.setattr(batch_repo,'get_research',lambda _: {'files':[{'file_path':str(first)},{'file_path':str(second)}]})
    original=corpus_governance_service.add_reference_document
    calls=[]
    def add(**kwargs):
        calls.append(kwargs['file_path'])
        return original(**kwargs) if len(calls)==1 else {'success':False,'error':'Safe second-part failure'}
    monkeypatch.setattr(corpus_governance_service,'add_reference_document',add)
    with base_repo.get_session() as db:
        before=[db.query(model).count() for model in (Document,ReferenceCorpusVersion,ReviewDecisionRecord)]
    import pytest
    with pytest.raises(ValueError):
        final_acceptance_service.accept_report(dict(report_repo.get_report(rid), research_id=901237), {'username':'test_admin','role':'system_admin'})
    assert len(calls)==2
    with base_repo.get_session() as db:
        assert before==[db.query(model).count() for model in (Document,ReferenceCorpusVersion,ReviewDecisionRecord)]
    assert report_repo.get_report(rid)['review_status']=='pending_review'
