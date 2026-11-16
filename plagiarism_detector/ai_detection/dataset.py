# -*- coding: utf-8 -*-
"""Provenance-first dataset validation for Arabic AI-writing research.

This module deliberately validates metadata, not AI authorship.  In particular,
it never derives a provenance label from a detector score.
"""
from __future__ import annotations

from .provenance import assess_split_leakage, find_exact_duplicates

REQUIRED_FIELDS = {
    'sample_id', 'document_id', 'text', 'provenance_label', 'generator_family',
    'editing_category', 'academic_domain', 'collection_method', 'license_permission',
    'annotation_confidence', 'data_origin',
}
PROVENANCE = {'HUMAN', 'AI_GENERATED', 'HUMAN_AI_LIGHT_EDIT', 'HUMAN_AI_HEAVY_EDIT', 'AI_HUMAN_EDIT', 'MIXED'}


def validate_record(record: dict) -> list[str]:
    missing = sorted(field for field in REQUIRED_FIELDS if field not in record)
    errors = [f'missing:{field}' for field in missing]
    if record.get('provenance_label') not in PROVENANCE:
        errors.append('invalid:provenance_label')
    if not str(record.get('text', '')).strip(): errors.append('invalid:empty_text')
    confidence = record.get('annotation_confidence')
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append('invalid:annotation_confidence')
    if not isinstance(record.get('license_permission'), bool): errors.append('invalid:license_permission')
    return errors


def assess_dataset_readiness(records: list[dict]) -> dict:
    errors = {str(r.get('sample_id', i)): validate_record(r) for i, r in enumerate(records)}
    invalid = {key: value for key, value in errors.items() if value}
    origins = {r.get('data_origin') for r in records}
    labels = {r.get('provenance_label') for r in records}
    document_ids = [r.get('document_id') for r in records]
    # Multiple passages from a document are valid.  They become a risk only if
    # they occur in more than one split; this is checked separately.
    duplicate_documents = len(document_ids) != len(set(document_ids))
    split_leakage = assess_split_leakage(records)
    exact_duplicates = find_exact_duplicates(records)
    genuine = any(origin not in {'DEVELOPER_SYNTHETIC', 'SYNTHETIC'} for origin in origins)
    required_labels = {'HUMAN', 'AI_GENERATED', 'HUMAN_AI_LIGHT_EDIT', 'AI_HUMAN_EDIT'}
    scientifically_ready = (
        not invalid and genuine and required_labels <= labels
        and split_leakage['has_declared_splits'] and not split_leakage['has_leakage']
        and not exact_duplicates
    )
    return {
        'records': len(records), 'invalid_records': invalid,
        'data_origins': sorted(str(o) for o in origins), 'labels': sorted(str(label) for label in labels),
        'duplicate_document_ids': duplicate_documents,
        'split_leakage': split_leakage,
        'exact_duplicate_groups': exact_duplicates,
        'scientific_readiness': 'READY' if scientifically_ready else 'UNVERIFIED',
        'reason': None if scientifically_ready else 'Requires provenance-labelled, source-disjoint non-synthetic Arabic academic data.',
    }
