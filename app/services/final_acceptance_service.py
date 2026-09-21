"""Commit approval and corpus governance together, preserving original files."""
import json
from datetime import datetime
from app.repositories import base_repo, thesis_repo, batch_repo
from app.models.schema import LegacyReport, ReviewDecisionRecord
from app.models.research_schema import Research
from app.workflow.statuses import validate_review_transition, derive_legacy_status
from app.services import corpus_governance_service, audit_service


def accept_report(report, actor):
    entries = []
    if report.get('is_combined_thesis') and report.get('thesis_id'):
        thesis = thesis_repo.get_thesis(report['thesis_id'])
        if (not thesis or thesis.get('is_stale') or thesis.get('combined_report_id') != report['id']
                or report.get('is_complete_thesis') is False):
            raise ValueError('لا يمكن اعتماد تقرير رسالة غير مكتمل أو لا يمثل الإصدار الحالي')
        from app.models.research_schema import ThesisPart
        with base_repo.get_session() as db:
            parts = db.query(ThesisPart).filter_by(thesis_id=report['thesis_id'], is_detached=0).order_by(ThesisPart.sort_order, ThesisPart.id).all()
            entries = [{'id': p.id, 'thesis_id': p.thesis_id, 'part_title': p.part_title,
                        'file_path': p.file_path, 'original_filename': p.original_filename,
                        'file_hash': p.file_hash} for p in parts]
        if not entries:
            raise ValueError('لا توجد أجزاء صالحة لإضافة الرسالة إلى المراجع')
    elif report.get('research_id'):
        entries = (batch_repo.get_research(report['research_id']) or {}).get('files', [])
    if not entries:
        entries = [{'file_path': report.get('final_file_path') or report.get('file_path', ''),
                    'raw_text': report.get('final_full_text') or ' '.join(s.get('text', '') for s in report.get('segments', [])),
                    'original_filename': report.get('file_name', '')}]
    references = []
    timestamp = datetime.utcnow()
    with base_repo.get_session() as db:
        row = db.get(LegacyReport, report['id'])
        if not row or row.scan_status != 'completed':
            raise ValueError('لا يمكن اعتماد تقرير غير مكتمل الفحص')
        previous = row.review_status or 'pending_review'
        if previous == 'final_accepted':
            raise ValueError('تم اعتماد هذا التقرير مسبقاً')
        if not validate_review_transition(previous, 'final_accepted'):
            raise ValueError('انتقال تحكيمي غير مسموح به')
        for entry in entries:
            if entry.get('file_hash'):
                from app.services.integrity_service import compute_stream_sha256
                actual_hash, _ = compute_stream_sha256(entry['file_path'])
                if actual_hash != entry['file_hash']:
                    raise ValueError('تغيرت بصمة الملف الأصلي؛ لم يتم اعتماد التقرير')
            provenance = {'source_type': 'accepted_thesis_part' if entry.get('thesis_id') else 'accepted_research',
                          'research_id': report.get('research_id'), 'report_id': report['id'],
                          'thesis_id': report.get('thesis_id'), 'part_id': entry.get('id') if entry.get('thesis_id') else None,
                          'approving_admin_id': actor.get('id'), 'approving_admin': actor.get('username'),
                          'approval_timestamp': timestamp.isoformat() + 'Z'}
            result = corpus_governance_service.add_reference_document(
                title=report.get('title', '') + (' — ' + entry['part_title'] if entry.get('part_title') else ''),
                author=report.get('author', ''), category=report.get('category', 'عام'),
                file_path=entry.get('file_path', ''), raw_text=entry.get('raw_text', ''),
                original_filename=entry.get('original_filename', ''), added_by=actor.get('username', ''),
                notes=json.dumps(provenance, ensure_ascii=False), transaction_session=db)
            if not result.get('success'):
                if result.get('is_duplicate') and result.get('existing_id'):
                    result = dict(result, id=result['existing_id'], reference_id=result.get('existing_reference_id'))
                else:
                    raise ValueError(result.get('error') or 'تعذر إضافة المرجع؛ لم يتم اعتماد التقرير')
            references.append(result)
        row.review_status = 'final_accepted'
        row.status = derive_legacy_status(row.scan_status, row.review_status)
        data = json.loads(row.report_json or '{}')
        data.update(review_status=row.review_status, status=row.status)
        row.report_json = json.dumps(data, ensure_ascii=False)
        research = db.query(Research).filter(Research.report_id == report['id']).first()
        if research: research.review_status = row.review_status
        if report.get('thesis_id') and report.get('is_combined_thesis'):
            from app.repositories.thesis_repo import Thesis
            thesis = db.get(Thesis, report['thesis_id'])
            if thesis: thesis.review_status = row.review_status
        db.add(ReviewDecisionRecord(report_id=report['id'], research_id=report.get('research_id'),
                                   thesis_id=report.get('thesis_id'), report_revision=report.get('revision_number', 1),
                                   previous_review_status=previous, new_review_status=row.review_status,
                                   decision=row.review_status, reviewer=actor.get('username', ''),
                                   reviewer_user_id=actor.get('id'), reviewer_role_snapshot=actor.get('role', ''),
                                   comment=json.dumps({'approval_timestamp': timestamp.isoformat()+'Z',
                                                       'references': references}, ensure_ascii=False)))
    for reference in references:
        if reference.get('success'):
            audit_service.record_event(action='reference.added', category='reference', user=actor,
                                       object_type='reference_document', object_id=str(reference['id']),
                                       research_id=report.get('research_id'), report_id=report['id'],
                                       metadata={'reference_id': reference.get('reference_id'),
                                                 'corpus_version': reference.get('corpus_version')})
    return references
