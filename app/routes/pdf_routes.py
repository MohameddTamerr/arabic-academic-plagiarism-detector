"""Authenticated offline PDF rendering from stored records, never client paths."""
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, send_file, render_template
from app.repositories import report_repo, thesis_repo, base_repo
from app.models.schema import Document
from app.services.document_preview_service import DocumentPreviewError, ensure_pdf_preview
from app.security.authorization import (require_permission, get_authenticated_user,
                                        can_view_report, can_view_thesis)
from app.security.permissions import Permission
import config
import io
import logging

pdf_bp = Blueprint('pdf_bp', __name__)
logger = logging.getLogger(__name__)


def _serve_pdf_with_pdfium(path: Path, action: str):
    """Fallback renderer for frozen Windows builds when PyMuPDF cannot open a valid PDF."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    page_count = len(document)
    if not 0 < page_count <= config.MAX_PDF_PAGES:
        return jsonify(error='تعذر عرض هذا المستند بأمان'), 400
    if action == 'info':
        return jsonify(page_count=page_count, coordinates_available=False)

    number = request.args.get('page', 1, type=int)
    if number is None or not 1 <= number <= page_count:
        return jsonify(error='رقم الصفحة غير صالح'), 400
    if action == 'highlights':
        return jsonify(highlights=[])
    if action == 'export':
        return send_file(
            path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{path.stem}_original.pdf',
        )

    page = document[number - 1]
    if action == 'locate':
        payload = request.get_json(silent=True) or {}
        target_text = str(payload.get('text') or '')[:4000].strip()
        page_width, page_height = page.get_size()
        rects = []
        if target_text:
            try:
                text_page = page.get_textpage()
                searcher = text_page.search(target_text)
                occurrence = searcher.get_next()
                if occurrence:
                    start, count = occurrence
                    rect_count = text_page.count_rects(start, count)
                    for rect_index in range(rect_count):
                        left, bottom, right, top = text_page.get_rect(rect_index)
                        rects.append([left, page_height - top, right, page_height - bottom])
            except Exception:
                logger.debug("PDFium could not locate source evidence text", exc_info=True)
        return jsonify(rects=rects, page_width=page_width, page_height=page_height)

    bitmap = page.render(scale=1.25)
    image = bitmap.to_pil()
    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    response = Response(output.getvalue(), mimetype='image/png')
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def _resolve(kind, record_id):
    actor = get_authenticated_user()
    if kind == 'report':
        record = report_repo.get_report(record_id)
        if not record:
            return None, 404
        if not can_view_report(actor, record):
            return None, 403
        # Parts retain their own file-local page numbering.
        if record.get('thesis_part_id'):
            part = thesis_repo.get_thesis_part(record['thesis_part_id'])
            return (part or {}).get('file_path'), 200
        if record.get('files') and len(record['files']) > 1:
            index = request.args.get('file_index', type=int)
            if index is None or not 0 <= index < len(record['files']):
                return None, 400
            return record['files'][index].get('path') or record['files'][index].get('file_path'), 200
        if record.get('research_id'):
            from app.models.research_schema import ResearchFile
            with base_repo.get_session() as db:
                files = db.query(ResearchFile).filter_by(research_id=record['research_id']).order_by(ResearchFile.file_order).all()
                if files:
                    index = request.args.get('file_index', type=int)
                    if index is None and len(files) == 1:
                        index = 0
                    if index is None or not 0 <= index < len(files):
                        return None, 400
                    return files[index].file_path, 200
        return record.get('file_path') or record.get('final_file_path'), 200
    if kind == 'reference':
        with base_repo.get_session() as db:
            record = db.get(Document, int(record_id))
            return (record.file_path, 200) if record else (None, 404)
    if kind == 'part':
        part = thesis_repo.get_thesis_part(int(record_id))
        if not part:
            return None, 404
        thesis = thesis_repo.get_thesis(part['thesis_id'])
        if not can_view_thesis(actor, thesis):
            return None, 403
        return part['file_path'], 200
    return None, 404


@pdf_bp.route('/source-viewer/<int:record_id>')
@require_permission(Permission.REPORT_VIEW)
def source_evidence_viewer(record_id):
    """Standalone authenticated source view used by evidence links."""
    return render_template(
        'source_viewer.html',
        source_id=record_id,
        source_page=max(1, request.args.get('page', 1, type=int) or 1),
        source_text=(request.args.get('text') or '')[:4000],
        source_title=(request.args.get('title') or 'الرسالة أو الجزء المصدر')[:500],
        source_kind='reference',
    )


@pdf_bp.route('/source-report-viewer/<record_id>')
@require_permission(Permission.REPORT_VIEW)
def source_report_evidence_viewer(record_id):
    """Open a preliminary/rejected historical report at its matched passage."""
    return render_template(
        'source_viewer.html',
        source_id=record_id,
        source_page=max(1, request.args.get('page', 1, type=int) or 1),
        source_text=(request.args.get('text') or '')[:4000],
        source_title=(request.args.get('title') or 'بحث سابق محل المقارنة')[:500],
        source_kind='report',
    )


@pdf_bp.route('/api/pdf/<kind>/<record_id>/<action>', methods=['GET', 'POST'])
@require_permission(Permission.REPORT_VIEW)
def view_pdf(kind, record_id, action):
    if kind not in ('report', 'reference', 'part') or action not in ('info', 'page', 'highlights', 'export', 'locate', 'evidence-index'):
        return jsonify(error='المستند غير متاح'), 404
    path = Path()
    try:
        value, status = _resolve(kind, record_id)
        if status != 200:
            return jsonify(error='غير مصرح أو تعذر تحديد المستند وصفحاته'), status
        source_path = Path(value or '')
        if not value or not source_path.is_file():
            logger.warning("PDF source is unavailable for %s record %s", kind, record_id)
            return jsonify(error='المستند الأصلي غير متاح لهذا السجل'), 404
        try:
            path = ensure_pdf_preview(source_path)
        except DocumentPreviewError as exc:
            logger.warning("Document preview is unavailable for %s: %s", source_path, exc)
            return jsonify(error=str(exc)), 422
        import fitz
        with fitz.open(str(path)) as doc:
            if doc.is_encrypted or not 0 < len(doc) <= config.MAX_PDF_PAGES:
                return jsonify(error='تعذر عرض هذا المستند بأمان'), 400
            if action == 'info':
                coordinates_available = any(bool(pdf_page.get_text('words')) for pdf_page in doc)
                return jsonify(page_count=len(doc), coordinates_available=coordinates_available)
            if action == 'evidence-index':
                return _get_evidence_index(kind, record_id, doc)
            number = request.args.get('page', 1, type=int)
            if number is None or not 1 <= number <= len(doc):
                return jsonify(error='رقم الصفحة غير صالح'), 400
            page = doc[number-1]
            if page.rect.width * page.rect.height > 12_000_000:
                return jsonify(error='حجم الصفحة يتجاوز حدود العرض الآمن'), 400

            if action == 'highlights':
                return _get_page_highlights(kind, record_id, number, page, doc.page_count)

            if action == 'locate':
                payload = request.get_json(silent=True) or {}
                target_text = str(payload.get('text') or '')[:4000].strip()
                page_text = page.get_text()
                rects = _get_text_rects(page, target_text, page_text)
                return jsonify(
                    rects=[[rect.x0, rect.y0, rect.x1, rect.y1] for rect in rects],
                    page_width=page.rect.width,
                    page_height=page.rect.height,
                )

            if action == 'export':
                return _export_highlighted_pdf(kind, record_id, path)

            png = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).tobytes('png')
            response = Response(png, mimetype='image/png')
            response.headers['Cache-Control'] = 'private, no-store'
            return response
    except OSError as exc:
        logger.warning(
            "PyMuPDF failed for %s record %s; using PDFium fallback: %s",
            kind, record_id, exc,
        )
        try:
            return _serve_pdf_with_pdfium(path, action)
        except Exception:
            logger.exception("PDFium fallback failed for %s record %s", kind, record_id)
            return jsonify(error='تعذر عرض مستند PDF المحلي'), 400
    except Exception:
        logger.exception("Failed to serve PDF action %s for %s record %s", action, kind, record_id)
        return jsonify(error='تعذر عرض مستند PDF المحلي'), 400


def _get_text_rects(page, search_text, page_text):
    """Shared helper: Find rectangles for search_text on page, handling Arabic normalization."""
    from plagiarism_detector.preprocessing.normalizer import normalize_light
    import re

    rects = []
    if not search_text:
        return rects

    # Try direct search first
    try:
        found_rects = page.search_for(search_text)
        if found_rects:
            return found_rects
    except Exception:
        pass

    # Try with normalization (Arabic diacritics, etc.)
    try:
        normalized_search = normalize_light(search_text)
        normalized_page = normalize_light(page_text)

        search_pattern = re.escape(normalized_search)
        for match in re.finditer(search_pattern, normalized_page):
            start_pos = match.start()
            try:
                words = page.get_text("words")
                char_pos = 0
                current_rects = []

                for word_info in words:
                    word_text = word_info[4]
                    if not word_text.strip():
                        char_pos += len(word_text)
                        continue

                    if char_pos <= start_pos < char_pos + len(word_text):
                        current_rects = []

                    if start_pos <= char_pos < start_pos + len(normalized_search):
                        current_rects.append(word_info[:4])
                    elif current_rects and char_pos >= start_pos + len(normalized_search):
                        break

                    char_pos += len(word_text)

                if current_rects:
                    x0 = min(r[0] for r in current_rects)
                    y0 = min(r[1] for r in current_rects)
                    x1 = max(r[2] for r in current_rects)
                    y1 = max(r[3] for r in current_rects)
                    import fitz
                    rects.append(fitz.Rect(x0, y0, x1, y1))
                    break
            except Exception:
                pass
    except Exception:
        pass

    return rects


def _get_segment_rects(segment, page, page_text):
    """Get rectangles for a single segment, with error tolerance."""
    member_texts = segment.get('member_texts') or [
        segment.get('text') or segment.get('suspect_text') or ''
    ]
    rects = []
    seen = set()
    for search_text in member_texts:
        if not search_text or len(search_text.strip()) < 3:
            continue
        for rect in _get_text_rects(page, search_text, page_text):
            key = tuple(round(float(value), 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
            if key not in seen:
                rects.append(rect)
                seen.add(key)
    return rects


def _is_highlightable_evidence(segment):
    """Only real matched evidence may appear in the PDF overlay."""
    status = str(segment.get('status') or '').strip().lower()
    match_type = str(segment.get('match_type') or '').strip().upper()
    if status in ('copied', 'paraphrased', 'cited'):
        return True
    if status in ('original', 'common', 'common_text', 'excluded'):
        return False
    return match_type in {
        'EXACT', 'DIRECT', 'DIRECT COPY', 'PARAPHRASE', 'CITED', 'CITED QUOTE'
    }


def _segment_scope_matches(segment, evidence_scope):
    if evidence_scope is None:
        return True
    segment_scope = segment.get('part_id')
    if segment_scope is None:
        segment_scope = segment.get('file_index')
    return segment_scope == evidence_scope


def _segment_page_number(segment, total_pages):
    raw_page = segment.get('page_number') or segment.get('suspect_page')
    try:
        page_number = int(raw_page)
    except (TypeError, ValueError):
        return None
    return page_number if 1 <= page_number <= total_pages else None


def _infer_unpaged_evidence_pages(document, indexed_segments):
    """Locate legacy DOCX evidence that was stored before page numbers existed."""
    unresolved = dict(indexed_segments)
    inferred = {}
    for page_number, page in enumerate(document, start=1):
        if not unresolved:
            break
        try:
            page_text = page.get_text()
        except Exception:
            page_text = ''
        for position, segment in list(unresolved.items()):
            if _get_segment_rects(segment, page, page_text):
                inferred[position] = page_number
                unresolved.pop(position, None)
    return inferred


def _get_evidence_index(kind, record_id, document):
    """Return a compact ordered index used to jump directly between matches."""
    if kind != 'report':
        return jsonify(items=[], total=0)

    total_pages = len(document)
    report = report_repo.get_report(record_id) or {}
    segments = report.get('segments') or report.get('matches') or []
    evidence_scope = request.args.get('part_id', type=int)
    if evidence_scope is None:
        evidence_scope = request.args.get('file_index', type=int)

    candidates = []
    unpaged = []
    for position, segment in enumerate(segments):
        if not _is_highlightable_evidence(segment) or not _segment_scope_matches(segment, evidence_scope):
            continue
        page_number = _segment_page_number(segment, total_pages)
        candidates.append((position, segment, page_number))
        if page_number is None:
            unpaged.append((position, segment))

    inferred_pages = _infer_unpaged_evidence_pages(document, unpaged) if unpaged else {}
    items = []
    seen = set()
    for position, segment, stored_page_number in candidates:
        page_number = stored_page_number or inferred_pages.get(position)
        if page_number is None:
            continue

        text = str(segment.get('text') or segment.get('suspect_text') or '').strip()
        key = (
            page_number,
            text[:160],
            str(segment.get('source_id') or segment.get('source_title') or ''),
            str(segment.get('status') or segment.get('match_type') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append({
            'page': page_number,
            'text': text,
            'status': segment.get('status') or '',
            'match_type': segment.get('match_type') or '',
            'source_title': segment.get('source_title') or '',
            'page_inferred': stored_page_number is None,
            'order': position,
        })

    items.sort(key=lambda item: (item['page'], item['order']))
    for item in items:
        item.pop('order', None)
    return jsonify(items=items, total=len(items))


def _get_page_highlights(kind, record_id, page_number, page, total_pages):
    """Extract highlight coordinates for evidence on a specific page."""
    highlights = []

    # Get page evidence
    if kind == 'report':
        evidence_scope = request.args.get('part_id', type=int)
        if evidence_scope is None:
            evidence_scope = request.args.get('file_index', type=int)
        page_data = report_repo.get_report_page_evidence(
            report_id=record_id,
            page_number=page_number,
            part_id=evidence_scope
        )
        segments = page_data.get('segments', [])
        # Legacy DOCX reports stored valid matches without page numbers. Match
        # those passages against the generated PDF preview on demand so old
        # reports regain highlights without rewriting their signed payloads.
        report = report_repo.get_report(record_id) or {}
        all_segments = report.get('segments') or report.get('matches') or []
        segments.extend(
            segment for segment in all_segments
            if _is_highlightable_evidence(segment)
            and _segment_page_number(segment, total_pages) is None
            and _segment_scope_matches(segment, evidence_scope)
        )
    else:
        return jsonify(highlights=[])

    # Get page text for normalization context
    try:
        page_text = page.get_text()
    except Exception:
        page_text = ""

    # Process each segment
    for seg in segments:
        if not _is_highlightable_evidence(seg):
            continue

        rects = _get_segment_rects(seg, page, page_text)
        if rects:
            status = seg.get('status', '')
            match_type = (seg.get('match_type') or '').upper()

            if status == 'copied' or match_type in ('EXACT', 'DIRECT', 'DIRECT COPY'):
                color = '#dc2626'
            elif status == 'paraphrased' or match_type == 'PARAPHRASE':
                color = '#d97706'
            else:
                color = '#059669'

            for rect in rects:
                highlights.append({
                    'rect': [rect.x0, rect.y0, rect.x1, rect.y1],
                    # PyMuPDF search rectangles are expressed in PDF points, not
                    # in the 1.25x PNG pixels returned by the page endpoint.
                    # Supplying the page coordinate space lets the browser align
                    # the SVG at every rendered width without relying on that
                    # implementation-specific raster scale.
                    'page_width': page.rect.width,
                    'page_height': page.rect.height,
                    'color': color,
                    'status': status,
                    'match_type': match_type,
                    'text': seg.get('text') or seg.get('suspect_text', ''),
                    'source_title': seg.get('source_title', ''),
                    'source_author': seg.get('source_author', ''),
                    'pct': seg.get('pct') or seg.get('score'),
                    'matched_text': seg.get('matched_text') or seg.get('source_text', ''),
                    'source_id': seg.get('source_id'),
                    'source_report_id': seg.get('source_report_id'),
                    'source_page': seg.get('source_page'),
                    'evidence_segment_count': seg.get('evidence_segment_count', 1),
                })

    return jsonify(highlights=highlights)


def _export_highlighted_pdf(kind, record_id, original_path):
    """Export PDF with persistent highlight annotations."""
    if kind != 'report':
        return jsonify(error='تصدير PDF متاح فقط للتقارير'), 400

    try:
        import fitz

        # Export is document-scoped.  The page-evidence repository API is
        # intentionally page-scoped and therefore returns nothing for
        # page_number=None; read the report payload once and group it below.
        report = report_repo.get_report(record_id) or {}
        all_segments = report.get('segments') or report.get('matches') or []
        file_index = request.args.get('file_index', type=int)
        if file_index is not None:
            all_segments = [
                segment for segment in all_segments
                if segment.get('file_index') == file_index
            ]

        # Create a copy of the document in memory
        output_doc = fitz.open(str(original_path))

        # Organize segments by page for efficient processing
        segments_by_page = {}
        for seg in all_segments:
            if seg.get('status') not in ('copied', 'paraphrased', 'cited'):
                continue
            raw_page_number = seg.get('page_number') or seg.get('suspect_page')
            try:
                p_num = int(raw_page_number)
            except (TypeError, ValueError):
                continue
            if p_num > 0:
                if p_num not in segments_by_page:
                    segments_by_page[p_num] = []
                segments_by_page[p_num].append(seg)

        # Process each page with segments
        for page_num, segs in segments_by_page.items():
            if not (1 <= page_num <= len(output_doc)):
                continue

            page = output_doc[page_num - 1]
            try:
                page_text = page.get_text()
            except Exception:
                page_text = ""

            # Add highlight annotations
            for seg in segs:
                rects = _get_segment_rects(seg, page, page_text)
                if not rects:
                    continue

                status = seg.get('status', '')
                match_type = (seg.get('match_type') or '').upper()

                # Determine annotation color and content
                if status == 'copied' or match_type in ('EXACT', 'DIRECT', 'DIRECT COPY'):
                    color = (1, 0, 0)  # Red
                    annot_type = 'Highlight'
                elif status == 'paraphrased' or match_type == 'PARAPHRASE':
                    color = (1, 0.6, 0)  # Orange
                    annot_type = 'Underline'
                else:
                    color = (0, 1, 0)  # Green
                    annot_type = 'Highlight'

                # Add annotation for each rect
                for rect in rects:
                    try:
                        if annot_type == 'Highlight':
                            annot = page.add_highlight_annot(rect)
                        else:
                            annot = page.add_underline_annot(rect)

                        if annot:
                            annot.set_colors({"stroke": color})
                            # Add popup content
                            annot.set_info({
                                "content": f"{seg.get('source_title', 'مرجع')} - {status}"
                            })
                    except Exception:
                        # Skip this annotation if it fails
                        pass

        # Save to in-memory buffer
        output_buffer = io.BytesIO()
        output_doc.save(output_buffer)
        output_buffer.seek(0)
        output_doc.close()

        # Generate filename
        original_name = Path(original_path).stem
        filename = f"{original_name}_highlighted.pdf"

        return send_file(
            output_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception:
        logger.exception("Failed to export highlighted PDF for report %s", record_id)
        return jsonify(error='فشل في تصدير PDF المؤشر عليه'), 400
