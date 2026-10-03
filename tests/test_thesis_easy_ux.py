from pathlib import Path

from app.services import thesis_service


ROOT = Path(__file__).resolve().parent.parent


def test_easy_thesis_upload_flow_is_exposed_in_ui():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'رفع وفحص رسالة كاملة' in html
    assert 'id="create-thesis-files"' in html
    assert 'multiple hidden' in html
    assert 'handleCreateThesisDrop(event)' in html
    assert "form.append('files[]', item.file)" in html
    assert "auto_scan: '1'" in html
    assert 'إنشاء الرسالة وبدء فحص كل الأجزاء' in html
    assert "['queued', 'scanning', 'processing', 'running']" in html


def test_auto_combines_once_when_all_parts_complete(monkeypatch):
    thesis_id = 987654321
    thesis = {
        'parts': [
            {'scan_status': 'completed', 'report_id': 'part-report-a'},
            {'scan_status': 'completed', 'report_id': 'part-report-b'},
        ]
    }
    calls = []
    monkeypatch.setattr(thesis_service.thesis_repo, 'get_thesis', lambda value: thesis)
    monkeypatch.setattr(
        thesis_service,
        'generate_combined_thesis_report',
        lambda value: (calls.append(value) or True, {'id': 'combined'}, 'ok'),
    )
    thesis_service._AUTO_COMBINED_SIGNATURES = {
        item for item in thesis_service._AUTO_COMBINED_SIGNATURES if item[0] != thesis_id
    }

    thesis_service._auto_generate_combined_report_if_ready(thesis_id)
    thesis_service._auto_generate_combined_report_if_ready(thesis_id)

    assert calls == [thesis_id]


def test_auto_combine_waits_for_every_part(monkeypatch):
    thesis_id = 987654322
    monkeypatch.setattr(
        thesis_service.thesis_repo,
        'get_thesis',
        lambda value: {
            'parts': [
                {'scan_status': 'completed', 'report_id': 'done'},
                {'scan_status': 'queued', 'report_id': None},
            ]
        },
    )
    calls = []
    monkeypatch.setattr(
        thesis_service,
        'generate_combined_thesis_report',
        lambda value: (calls.append(value) or True, {}, 'ok'),
    )

    thesis_service._auto_generate_combined_report_if_ready(thesis_id)

    assert calls == []
