from pathlib import Path

import fitz
from flask import Flask

from app.routes import pdf_routes
from app.services import document_preview_service


def _make_text_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((40, 80), "unique evidence text", fontsize=12)
    document.save(path)
    document.close()


def test_highlight_payload_exposes_pdf_coordinate_space(tmp_path, monkeypatch):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)
    segment = {
        "status": "copied",
        "text": "unique evidence text",
        "page_number": 1,
    }
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report_page_evidence",
        lambda **_kwargs: {"segments": [segment]},
    )

    app = Flask(__name__)
    with app.test_request_context("/"):
        with fitz.open(pdf_path) as document:
            payload = pdf_routes._get_page_highlights(
                "report", "report-1", 1, document[0], 1
            ).get_json()

    assert len(payload["highlights"]) == 1
    highlight = payload["highlights"][0]
    assert highlight["page_width"] == 300
    assert highlight["page_height"] == 400


def test_original_segment_with_match_type_is_not_highlighted(tmp_path, monkeypatch):
    pdf_path = tmp_path / "original.pdf"
    _make_text_pdf(pdf_path)
    segment = {
        "status": "original",
        "match_type": "ORIGINAL",
        "text": "unique evidence text",
        "pct": 0,
        "page_number": 1,
    }
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report_page_evidence",
        lambda **_kwargs: {"segments": [segment]},
    )

    app = Flask(__name__)
    with app.test_request_context("/"):
        with fitz.open(pdf_path) as document:
            payload = pdf_routes._get_page_highlights(
                "report", "report-1", 1, document[0], 1
            ).get_json()

    assert payload["highlights"] == []


def test_highlight_export_reads_document_evidence_and_filters_file(tmp_path, monkeypatch):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)
    segments = [
        {
            "status": "copied",
            "text": "unique evidence text",
            "page_number": "1",
            "file_index": 0,
        },
        {
            "status": "cited",
            "text": "unique evidence text",
            "page_number": 1,
            "file_index": 1,
        },
    ]
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report",
        lambda _report_id: {"segments": segments},
    )

    app = Flask(__name__)
    with app.test_request_context("/?file_index=0"):
        response = pdf_routes._export_highlighted_pdf(
            "report", "report-1", pdf_path
        )
        response.direct_passthrough = False
        exported_bytes = response.get_data()

    exported = fitz.open(stream=exported_bytes, filetype="pdf")
    try:
        annotations = list(exported[0].annots() or [])
    finally:
        exported.close()

    assert len(annotations) == 1


def test_pdfium_fallback_serves_info_and_page_for_valid_pdf(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)
    app = Flask(__name__)

    with app.test_request_context("/?page=1"):
        info = pdf_routes._serve_pdf_with_pdfium(pdf_path, "info").get_json()
        page_response = pdf_routes._serve_pdf_with_pdfium(pdf_path, "page")

    assert info == {"coordinates_available": False, "page_count": 1}
    assert page_response.mimetype == "image/png"
    assert page_response.get_data().startswith(b"\x89PNG\r\n\x1a\n")


def test_grouped_evidence_highlights_every_member_and_exposes_source_link_data(tmp_path, monkeypatch):
    pdf_path = tmp_path / "grouped.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((40, 80), "first connected sentence", fontsize=12)
    page.insert_text((40, 110), "second connected sentence", fontsize=12)
    document.save(pdf_path)
    document.close()
    segment = {
        "status": "paraphrased",
        "text": "first connected sentence second connected sentence",
        "member_texts": ["first connected sentence", "second connected sentence"],
        "source_id": 17,
        "source_page": 9,
        "matched_text": "source passage",
        "page_number": 1,
    }
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report_page_evidence",
        lambda **_kwargs: {"segments": [segment]},
    )

    app = Flask(__name__)
    with app.test_request_context("/"):
        with fitz.open(pdf_path) as source:
            payload = pdf_routes._get_page_highlights(
                "report", "report-1", 1, source[0], 1
            ).get_json()

    assert len(payload["highlights"]) == 2
    assert {item["source_id"] for item in payload["highlights"]} == {17}
    assert {item["source_page"] for item in payload["highlights"]} == {9}


def test_source_viewer_contains_new_tab_evidence_workflow():
    template = Path("templates/source_viewer.html").read_text(encoding="utf-8")
    viewer_js = Path("static/js/pdf-viewer.js").read_text(encoding="utf-8")

    assert "الرسالة/الجزء المصدر" in template
    assert "/locate?page=${page}" in template
    assert "source-highlight-overlay" in template
    assert "function openSourceEvidence" in viewer_js
    assert "window.open(url, '_blank'" in viewer_js


def test_docx_preview_is_converted_once_and_reused(tmp_path, monkeypatch):
    source = tmp_path / "research.docx"
    source.write_bytes(b"PK\x03\x04-test-docx")
    cache_dir = tmp_path / "previews"
    conversions = []

    monkeypatch.setattr(document_preview_service, "_preview_cache_dir", lambda: cache_dir)

    def fake_word_conversion(_source, destination):
        conversions.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _make_text_pdf(destination)

    monkeypatch.setattr(document_preview_service, "_convert_with_word", fake_word_conversion)

    first = document_preview_service.ensure_pdf_preview(source)
    second = document_preview_service.ensure_pdf_preview(source)

    assert first == second
    assert first.suffix == ".pdf"
    assert first.is_file()
    assert len(conversions) == 1


def test_docx_preview_falls_back_to_libreoffice(tmp_path, monkeypatch):
    source = tmp_path / "research.docx"
    source.write_bytes(b"PK\x03\x04-test-docx")
    cache_dir = tmp_path / "previews"
    fallbacks = []

    monkeypatch.setattr(document_preview_service, "_preview_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(
        document_preview_service,
        "_convert_with_word",
        lambda *_args: (_ for _ in ()).throw(document_preview_service.DocumentPreviewError("Word unavailable")),
    )

    def fake_libreoffice_conversion(_source, destination):
        fallbacks.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _make_text_pdf(destination)

    monkeypatch.setattr(document_preview_service, "_convert_with_libreoffice", fake_libreoffice_conversion)

    preview = document_preview_service.ensure_pdf_preview(source)

    assert preview.is_file()
    assert len(fallbacks) == 1


def test_evidence_index_returns_ordered_in_scope_matches(monkeypatch):
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report",
        lambda _report_id: {
            "segments": [
                {"status": "copied", "page_number": 4, "text": "second", "file_index": 0},
                {"status": "original", "page_number": 2, "text": "ignore", "file_index": 0},
                {"status": "paraphrased", "page_number": 2, "text": "first", "file_index": 0},
                {"status": "cited", "page_number": 1, "text": "other file", "file_index": 1},
            ]
        },
    )
    app = Flask(__name__)

    pdf_path = Path(__file__).parent / "_unused.pdf"
    document = fitz.open()
    for _ in range(5):
        document.new_page()
    with app.test_request_context("/?file_index=0"):
        payload = pdf_routes._get_evidence_index("report", "report-1", document).get_json()
    document.close()

    assert payload["total"] == 2
    assert [item["page"] for item in payload["items"]] == [2, 4]
    assert [item["text"] for item in payload["items"]] == ["first", "second"]


def test_legacy_unpaged_evidence_is_inferred_and_highlighted(tmp_path, monkeypatch):
    pdf_path = tmp_path / "legacy-docx-preview.pdf"
    _make_text_pdf(pdf_path)
    legacy_segment = {
        "status": "copied",
        "match_type": "DIRECT COPY",
        "page_number": None,
        "text": "unique evidence text",
        "source_title": "legacy source",
    }
    monkeypatch.setattr(pdf_routes.report_repo, "get_report", lambda _report_id: {"segments": [legacy_segment]})
    monkeypatch.setattr(
        pdf_routes.report_repo,
        "get_report_page_evidence",
        lambda **_kwargs: {"segments": []},
    )
    app = Flask(__name__)

    with app.test_request_context("/"):
        with fitz.open(pdf_path) as document:
            index_payload = pdf_routes._get_evidence_index("report", "legacy", document).get_json()
            highlight_payload = pdf_routes._get_page_highlights(
                "report", "legacy", 1, document[0], len(document)
            ).get_json()

    assert index_payload["total"] == 1
    assert index_payload["items"][0]["page"] == 1
    assert index_payload["items"][0]["page_inferred"] is True
    assert len(highlight_payload["highlights"]) == 1


def test_pdf_viewer_has_direct_evidence_navigation_controls():
    template = Path("templates/index.html").read_text(encoding="utf-8")
    viewer_js = Path("static/js/pdf-viewer.js").read_text(encoding="utf-8")

    assert "اذهب لأول تطابق" in template
    assert 'id="inline-evidence-prev"' in template
    assert 'id="inline-evidence-next"' in template
    assert "async function jumpToEvidence" in viewer_js
    assert "'/evidence-index'" in viewer_js
