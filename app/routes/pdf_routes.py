"""Authenticated offline PDF rendering from stored records, never client paths."""
from pathlib import Path
from flask import Blueprint, request, jsonify, Response
from app.repositories import report_repo, thesis_repo, base_repo
from app.models.schema import Document
from app.security.authorization import (require_permission, get_authenticated_user,
                                        can_view_report, can_view_thesis)
from app.security.permissions import Permission
import config

pdf_bp = Blueprint('pdf_bp', __name__)


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


@pdf_bp.route('/api/pdf/<kind>/<record_id>/<action>')
@require_permission(Permission.REPORT_VIEW)
def view_pdf(kind, record_id, action):
    if kind not in ('report', 'reference', 'part') or action not in ('info', 'page'):
        return jsonify(error='المستند غير متاح'), 404
    try:
        value, status = _resolve(kind, record_id)
        if status != 200:
            return jsonify(error='غير مصرح أو تعذر تحديد المستند وصفحاته'), status
        path = Path(value or '')
        if not path.is_file() or path.suffix.lower() != '.pdf':
            return jsonify(error='ملف PDF غير متاح لهذا السجل'), 404
        import fitz
        with fitz.open(str(path)) as doc:
            if doc.is_encrypted or not 0 < len(doc) <= config.MAX_PDF_PAGES:
                return jsonify(error='تعذر عرض هذا المستند بأمان'), 400
            if action == 'info':
                return jsonify(page_count=len(doc), coordinates_available=False)
            number = request.args.get('page', 1, type=int)
            if number is None or not 1 <= number <= len(doc):
                return jsonify(error='رقم الصفحة غير صالح'), 400
            page = doc[number-1]
            if page.rect.width * page.rect.height > 12_000_000:
                return jsonify(error='حجم الصفحة يتجاوز حدود العرض الآمن'), 400
            png = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).tobytes('png')
            response = Response(png, mimetype='image/png')
            response.headers['Cache-Control'] = 'private, no-store'
            return response
    except Exception:
        return jsonify(error='تعذر عرض مستند PDF المحلي'), 400
