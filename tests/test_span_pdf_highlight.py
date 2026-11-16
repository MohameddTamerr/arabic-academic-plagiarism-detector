import fitz

from app.routes import pdf_routes


def test_stage2_unresolvable_span_does_not_fall_back_to_full_sentence(tmp_path):
    path = tmp_path / "span.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((40, 60), "visible source text", fontsize=12)
    document.save(path)
    document.close()
    segment = {
        "text": "visible source text",
        "alignment_evidence": [{"kind": "lexical", "spans": [{"suspicious_text": "not on page"}]}],
    }
    with fitz.open(path) as pdf:
        assert pdf_routes._get_segment_rects(segment, pdf[0], pdf[0].get_text()) == []
