import socket

import pytest

from plagiarism_detector.ai_detection.analysis import unavailable_analysis
from plagiarism_detector.reporting.html_exporter import export_report_to_html
from plagiarism_detector.reporting.report_builder import analyze_academic_document


@pytest.mark.parametrize('enabled,reason', [(False, 'disabled'), (True, 'no_validated_model')])
def test_unavailable_has_no_fabricated_predictions(enabled, reason):
    result = unavailable_analysis(enabled)
    assert result['status'] == 'unavailable'
    assert result['reason'] == reason
    assert result['validation_status'] == 'no_validated_model'
    assert all(result[key] is None for key in (
        'estimated_ai_percentage', 'estimated_human_percentage',
        'uncertain_percentage', 'unanalyzed_percentage', 'model'))
    assert result['paragraphs'] == []


def test_shared_report_does_not_change_similarity_when_flag_enabled(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('AI status must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    text = 'هذا نص أكاديمي عربي لاختبار تحليل البحث والمقارنة بين المصادر المحلية.'
    pages = [{'page_number': 2, 'text': text}]
    disabled = analyze_academic_document(text, pages_data=pages,
        settings_override={'enable_experimental_ai_writing_analysis': False, 'enable_semantic_model': False})
    enabled = analyze_academic_document(text, pages_data=pages,
        settings_override={'enable_experimental_ai_writing_analysis': True, 'enable_semantic_model': False})
    assert enabled['ai_analysis']['reason'] == 'no_validated_model'
    for key in ('overall_pct', 'copied_pct', 'paraphrase_pct', 'segments', 'sources'):
        assert enabled[key] == disabled[key]


def test_export_never_presents_legacy_heuristic_as_authorship():
    exported = export_report_to_html({'ai_analysis': {'score': 99, 'indicator_level': 'high'}})
    assert 'لا يوجد نموذج مدقق' in exported
    assert 'الدرجة الاستئناسية' not in exported


def test_ai_initialization_failure_does_not_prevent_similarity(monkeypatch):
    from plagiarism_detector.reporting import report_builder
    text = 'هذا نص أكاديمي عربي لاختبار استمرار نتيجة المقارنة عند حدوث خطأ مستقل.'
    settings = {'enable_semantic_model': False}
    expected = analyze_academic_document(text, settings_override=settings)

    def fail(*args, **kwargs):
        raise RuntimeError('simulated AI failure')
    monkeypatch.setattr(report_builder, 'unavailable_analysis', fail)
    actual = analyze_academic_document(text, settings_override=settings)
    assert actual['ai_analysis']['reason'] == 'analysis_error'
    assert actual['ai_analysis']['estimated_ai_percentage'] is None
    for key in ('overall_pct', 'copied_pct', 'paraphrase_pct', 'segments', 'sources'):
        assert actual[key] == expected[key]
    assert 'تعذر تحليل' in export_report_to_html(actual)


def test_analyze_ai_failure_still_persists_report_and_independent_engine_statuses(monkeypatch):
    from app import create_app
    from plagiarism_detector.reporting import report_builder

    def fail(*args, **kwargs):
        raise RuntimeError('simulated AI failure')

    monkeypatch.setattr(report_builder, 'unavailable_analysis', fail)
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.post('/api/analyze', data={'text': 'نص أكاديمي عربي مستقل لفحص حفظ التقرير'})
        assert response.status_code == 200
        report = response.get_json()
        for path in (f"/api/reports/{report['id']}", f"/api/reports/{report['id']}/summary"):
            reopened = client.get(path)
            assert reopened.status_code == 200
            assert reopened.json['plagiarism_analysis'] == report['plagiarism_analysis'] == {'status': 'completed'}
            assert reopened.json['ai_analysis'] == report['ai_analysis']
            assert reopened.json['ai_analysis']['reason'] == 'analysis_error'
            assert reopened.json['overall_pct'] == report['overall_pct']


def test_legacy_heuristic_is_omitted_from_api_without_updating_stored_report():
    from app import create_app
    from app.repositories import report_repo

    report_id = 'legacy-ai-test'
    legacy = {'score': 99, 'estimated_ai_percentage': 99, 'indicator_level': 'high'}
    report_repo.save_report(report_id, 'Legacy test', 0, 0, 0, {'ai_analysis': legacy})
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        for path in (f'/api/reports/{report_id}', f'/api/reports/{report_id}/summary'):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json['ai_analysis'] == unavailable_analysis(True)
    assert report_repo.get_report(report_id)['ai_analysis'] == legacy


def test_analyze_document_ai_research_workflow(monkeypatch):
    """Test the experimental research AI detection workflow on CPU without network."""
    def no_network(*args, **kwargs):
        raise AssertionError('Network traffic prohibited during AI inference')
    monkeypatch.setattr(socket.socket, 'connect', no_network)

    from plagiarism_detector.ai_detection.analysis import analyze_document_ai_research

    p1 = "تعتبر المسؤولية الجنائية الناشئة عن سرقة الآثار ركيزة أساسية لحماية التراث الوطني في التشريعات المقارنة."
    p2 = "يولد جميع الناس أحراراً ومتساوين في الكرامة والحقوق وهم قد وهبوا العقل والوجدان وعليهم أن يعامل بعضهم بعضاً بروح الإخاء."
    text = f"{p1}\n\n{p2}"
    pages = [
        {'page_number': 1, 'text': p1},
        {'page_number': 2, 'text': p2}
    ]

    result = analyze_document_ai_research(text, pages_data=pages)
    assert result['status'] == 'completed'
    assert result['mode'] == 'research_experimental'
    assert result['validation_status'] == 'preliminary_academic_validation'
    assert result['paragraphs_count'] == 2
    assert result['total_words_analyzed'] > 0
    assert 0 <= result['estimated_ai_percentage'] <= 100
    assert 0 <= result['estimated_human_percentage'] <= 100

    para0 = result['paragraphs'][0]
    assert para0['page_number'] == 1
    assert para0['word_count'] == len(p1.split())
    assert 0 <= para0['ai_probability'] <= 1
    assert para0['classification'] in ('AI_GENERATED', 'HUMAN', 'UNCERTAIN')

    para1 = result['paragraphs'][1]
    assert para1['page_number'] == 2
    assert para1['word_count'] == len(p2.split())
    assert 0 <= para1['ai_probability'] <= 1

    # Empty text fails closed cleanly
    empty_res = analyze_document_ai_research("")
    assert empty_res['status'] == 'unavailable'


def test_research_mode_end_to_end_via_report_and_api(monkeypatch):
    """Verify end-to-end integration of AI research mode through reporting and API endpoints."""
    from app import create_app
    from app.repositories import report_repo
    from plagiarism_detector.ai_detection.analysis import public_ai_analysis
    from plagiarism_detector.reporting.report_builder import analyze_academic_document

    sample_text = "تعتبر حماية الآثار والتحف القديمة من أهم الواجبات القانونية التي تقع على عاتق الدولة للحفاظ على التراث الثقافي والتاريخي للأمة."

    # 1. Pipeline execution with research mode
    report = analyze_academic_document(
        sample_text,
        settings_override={'enable_ai_research_mode': True, 'enable_semantic_model': False}
    )
    assert report['ai_analysis']['status'] == 'completed'
    assert report['ai_analysis']['mode'] == 'research_experimental'
    assert report['overall_pct'] is not None

    # 2. public_ai_analysis preserves completed status
    public_payload = public_ai_analysis(report['ai_analysis'])
    assert public_payload['status'] == 'completed'
    assert public_payload['estimated_ai_percentage'] == report['ai_analysis']['estimated_ai_percentage']

    # 3. Persistence and API retrieval
    report_id = 'research-ai-e2e-test'
    report_repo.save_report(report_id, 'Research AI Test', 0, 0, 0, report)
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.get(f'/api/reports/{report_id}')
        assert response.status_code == 200
        fetched = response.get_json()
        assert fetched['ai_analysis']['status'] == 'completed'
        assert fetched['ai_analysis']['mode'] == 'research_experimental'
        assert fetched['ai_analysis']['estimated_ai_percentage'] is not None


