"""Exclude only references with explicit provenance for the work being rescanned."""
import json
from app.repositories import base_repo
from app.models.schema import Document


def reference_ids_for_work(research_id=None, thesis_id=None):
    if not research_id and not thesis_id:
        return set()
    excluded = set()
    with base_repo.get_session() as db:
        for doc in db.query(Document).filter(Document.notes.isnot(None)).all():
            try:
                provenance = json.loads(doc.notes)
            except (ValueError, TypeError):
                continue
            if not isinstance(provenance, dict):
                continue
            if ((research_id and provenance.get('research_id') == research_id)
                    or (thesis_id and provenance.get('thesis_id') == thesis_id)):
                excluded.add(doc.id)
    return excluded


def reference_ids_for_scan(scan_job_id):
    from app.models.research_schema import Research
    with base_repo.get_session() as db:
        research = db.query(Research).filter_by(scan_job_id=scan_job_id).first()
        research_id = research.id if research else None
    return reference_ids_for_work(research_id=research_id)
