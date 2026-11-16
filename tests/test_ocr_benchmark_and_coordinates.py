from plagiarism_detector.extraction.ocr_coordinates import OcrWordBox, image_bbox_to_pdf_rect
from tools.ocr_benchmark import score


def test_ocr_metrics_are_exact_for_normalized_equivalence():
    result = score('دِراسة  Arabic', 'دراسة Arabic')
    assert result['cer'] == 0.0 and result['wer'] == 0.0


def test_coordinate_mapping_is_scaled_and_refuses_untrusted_geometry():
    box = OcrWordBox('دراسة', 90, 100, 50, 200, 100, 0, 5)
    rect = image_bbox_to_pdf_rect(box, image_width=1000, image_height=500, page_rect=(0, 0, 500, 250), rotation=90)
    assert rect == {'x0': 50.0, 'y0': 25.0, 'x1': 150.0, 'y1': 75.0, 'coordinate_basis': 'rendered_page', 'rotation': 90}
    assert image_bbox_to_pdf_rect(OcrWordBox('x', 10, 0, 0, 1, 1, 0, 1), image_width=1, image_height=1, page_rect=(0,0,1,1)) is None
    assert image_bbox_to_pdf_rect(box, image_width=100, image_height=10, page_rect=(0,0,1,1)) is None
