# -*- coding: utf-8 -*-
"""Append-only, opt-in evidence review service for Stage 6."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from sqlalchemy import select

from app.reviewer_workflow_schema import EvidenceReviewDecision
from plagiarism_detector.reporting.reviewer_evidence import EXCLUSION_STATUS

DECISIONS = {'PENDING_REVIEW', 'ACCEPTED', 'REJECTED', 'NEEDS_REVIEW', EXCLUSION_STATUS}


class ReviewWorkflowError(ValueError):
    pass


def _row_dict(row, is_current=True):
    return {
        'id': row.id, 'report_id': row.report_id, 'evidence_id': row.evidence_id,
        'evidence_version': row.evidence_version, 'reviewer_id': row.reviewer_id,
        'reviewer_name': row.reviewer_name, 'reviewer_role': row.reviewer_role,
        'decision_type': row.decision_type, 'justification': row.justification,
        'source_ids': json.loads(row.source_ids_json or '[]'),
        'previous_decision_id': row.previous_decision_id, 'request_id': row.request_id,
        'created_at': row.created_at.isoformat() if row.created_at else '', 'is_current': is_current,
    }


def list_decisions(session, report_id: str) -> list[dict]:
    rows = session.execute(select(EvidenceReviewDecision).where(
        EvidenceReviewDecision.report_id == str(report_id)
    ).order_by(EvidenceReviewDecision.created_at, EvidenceReviewDecision.id)).scalars().all()
    referenced = {row.previous_decision_id for row in rows if row.previous_decision_id}
    return [_row_dict(row, row.id not in referenced) for row in rows]


def record_decision(session, *, report_id: str, evidence_id: str, evidence_version: str,
                    actor: dict, decision_type: str, justification: str,
                    source_ids=None, idempotency_key: str, expected_previous_decision_id=None,
                    allow_other_reviewer_revision: bool = False, request_id: str = '') -> dict:
    """Append an event; revision never updates/deletes a prior decision.

    ``expected_previous_decision_id`` supplies optimistic concurrency.  A
    repeated idempotency key returns its original event.
    """
    if decision_type not in DECISIONS:
        raise ReviewWorkflowError('UNKNOWN_DECISION_TYPE')
    if decision_type == EXCLUSION_STATUS and not str(justification or '').strip():
        raise ReviewWorkflowError('EXCLUSION_JUSTIFICATION_REQUIRED')
    actor_id = str(actor.get('id') or actor.get('username') or '')
    if not actor_id:
        raise ReviewWorkflowError('REVIEWER_ID_REQUIRED')
    existing = session.execute(select(EvidenceReviewDecision).where(
        EvidenceReviewDecision.idempotency_key == idempotency_key
    )).scalar_one_or_none()
    if existing:
        return _row_dict(existing)
    history = session.execute(select(EvidenceReviewDecision).where(
        EvidenceReviewDecision.report_id == str(report_id),
        EvidenceReviewDecision.evidence_id == evidence_id,
    ).order_by(EvidenceReviewDecision.created_at.desc(), EvidenceReviewDecision.id.desc())).scalars().all()
    current = next((row for row in history if not any(x.previous_decision_id == row.id for x in history)), None)
    current_id = current.id if current else None
    if expected_previous_decision_id != current_id:
        raise ReviewWorkflowError('STALE_DECISION_CONFLICT')
    if current and current.reviewer_id != actor_id and not allow_other_reviewer_revision:
        raise ReviewWorkflowError('OTHER_REVIEWER_DECISION_PROTECTED')
    row = EvidenceReviewDecision(
        id=str(uuid.uuid4()), idempotency_key=idempotency_key, report_id=str(report_id),
        evidence_id=evidence_id, evidence_version=evidence_version, reviewer_id=actor_id,
        reviewer_name=str(actor.get('username') or actor.get('full_name') or actor_id),
        reviewer_role=str(actor.get('role') or ''), decision_type=decision_type,
        justification=str(justification or '').strip(), source_ids_json=json.dumps(source_ids or [], ensure_ascii=False),
        previous_decision_id=current_id, request_id=request_id, created_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return _row_dict(row)
