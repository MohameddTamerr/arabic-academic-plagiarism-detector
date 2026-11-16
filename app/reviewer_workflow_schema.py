# -*- coding: utf-8 -*-
"""Opt-in Stage 6 storage schema.

This metadata is deliberately separate from ``app.models.schema.Base``.  The
normal application startup calls ``Base.metadata.create_all``; importing this
module therefore cannot create a production table.  Deployment must execute
the reviewed migration in STAGE6_DATABASE_MIGRATION_PLAN.md first.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, String, Text, Index
from sqlalchemy.orm import declarative_base

ReviewerWorkflowBase = declarative_base()


class EvidenceReviewDecision(ReviewerWorkflowBase):
    __tablename__ = 'evidence_review_decisions'
    id = Column(String(64), primary_key=True)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    report_id = Column(String(64), nullable=False, index=True)
    evidence_id = Column(String(80), nullable=False, index=True)
    evidence_version = Column(String(96), nullable=False, index=True)
    reviewer_id = Column(String(64), nullable=False, index=True)
    reviewer_name = Column(String(255), default='')
    reviewer_role = Column(String(64), default='')
    decision_type = Column(String(48), nullable=False)
    justification = Column(Text, default='')
    source_ids_json = Column(Text, default='[]')
    previous_decision_id = Column(String(64), nullable=True)
    request_id = Column(String(64), default='')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index('idx_evidence_review_current', 'report_id', 'evidence_id', 'created_at'),)


def create_reviewer_workflow_schema_for_isolated_testing(engine) -> None:
    """Explicit test/deployment hook; never called by application startup."""
    ReviewerWorkflowBase.metadata.create_all(bind=engine)
