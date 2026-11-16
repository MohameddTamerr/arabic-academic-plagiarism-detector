# -*- coding: utf-8 -*-
"""Immutable Stage 6 evidence views and deterministic reviewed coverage.

This module intentionally has no database dependency.  It derives a stable
catalogue from an already stored report, leaving Stage 2 raw evidence and its
score untouched.  Semantic candidates are displayed but cannot carry tokens
or alter coverage.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

EVIDENCE_VERSION = 'stage6_evidence_v1'
LEXICAL_KINDS = {'lexical'}
EXCLUSION_STATUS = 'EXCLUDED_WITH_JUSTIFICATION'


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]


def evidence_version(report: dict) -> str:
    """Version bound to immutable raw evidence, not mutable reviewer actions."""
    material = {
        'version': EVIDENCE_VERSION,
        'report_id': str(report.get('id') or report.get('report_id') or ''),
        'revision': report.get('revision_number', 1),
        'scoring_version': report.get('scoring_version', 'legacy'),
        'segments': [
            {
                'text': item.get('text', ''),
                'tokens': item.get('matched_token_indexes', []),
                'alignment': item.get('alignment_evidence', []),
            }
            for item in report.get('segments', [])
        ],
    }
    return f'{EVIDENCE_VERSION}:{_digest(material)}'


def build_evidence_catalog(report: dict) -> list[dict]:
    """Return one immutable review item per lexical/semantic source candidate.

    A source alternative remains an alternative; this function never chooses an
    alleged original.  Token indexes refer to the submitted segment's original
    tokenization, and source spans retain the Stage 2 Unicode offsets.
    """
    report_id = str(report.get('id') or report.get('report_id') or '')
    version = evidence_version(report)
    catalog: list[dict] = []
    for segment_index, segment in enumerate(report.get('segments') or []):
        if segment.get('is_bibliography') or segment.get('status') == 'suppressed':
            continue
        for alignment in segment.get('alignment_evidence') or []:
            source_id = alignment.get('source_reference_id') or alignment.get('source_id')
            token_indexes = sorted({int(i) for i in alignment.get('matched_suspicious_token_indexes', [])})
            canonical = {
                'segment_index': segment_index,
                'source_id': str(source_id or ''),
                'source_segment_number': alignment.get('source_segment_number'),
                'spans': alignment.get('spans', []),
                'tokens': token_indexes,
            }
            catalog.append({
                'evidence_id': f'lex-{_digest([report_id, version, canonical])}',
                'evidence_version': version,
                'kind': 'lexical',
                'segment_index': segment_index,
                'submitted_text': segment.get('text', ''),
                'submitted_page': segment.get('page_number'),
                'source_id': source_id,
                'source_title': alignment.get('source_title', ''),
                'source_page': alignment.get('source_page'),
                'source_segment_number': alignment.get('source_segment_number'),
                'source_spans': alignment.get('spans', []),
                'matched_token_indexes': token_indexes,
                'citation_links': segment.get('citation_links', []),
                'citation_linkage_status': segment.get('citation_linkage_status', 'NO_CITATION'),
                'source_verification_status': segment.get('source_verification_status', 'NOT_VERIFIED'),
                'review_required': True,
            })
        for semantic in segment.get('semantic_candidate_evidence') or []:
            source_id = semantic.get('source_reference_id') or semantic.get('source_id')
            canonical = {'segment_index': segment_index, 'source_id': str(source_id or ''), 'semantic': semantic}
            catalog.append({
                'evidence_id': f'sem-{_digest([report_id, version, canonical])}',
                'evidence_version': version,
                'kind': 'semantic_candidate',
                'segment_index': segment_index,
                'submitted_text': segment.get('text', ''),
                'submitted_page': segment.get('page_number'),
                'source_id': source_id,
                'source_title': semantic.get('source_title', ''),
                'source_page': semantic.get('source_page'),
                'semantic_score': semantic.get('semantic_score', semantic.get('score')),
                'matched_token_indexes': [],
                'source_spans': [],
                'coordinate_status': 'semantic_no_lexical_coordinates',
                'review_required': True,
            })
    return catalog


def calculate_reviewer_adjusted_coverage(report: dict, decisions: Iterable[dict]) -> dict:
    """Apply only current, authorized exclusion decisions to unique raw tokens.

    The denominator is the Stage 2 evaluated-token denominator.  Exclusion IDs
    that no longer exist or have a different evidence version are ignored and
    returned as stale; raw report fields are never mutated.
    """
    catalog = {item['evidence_id']: item for item in build_evidence_catalog(report)}
    current_version = evidence_version(report)
    raw_refs = {
        (segment_index, int(token))
        for segment_index, segment in enumerate(report.get('segments') or [])
        if not segment.get('is_bibliography') and segment.get('status') != 'suppressed'
        for token in (segment.get('matched_token_indexes') or [])
    }
    excluded: set[tuple[int, int]] = set()
    stale: list[str] = []
    applied: list[str] = []
    for decision in decisions:
        if decision.get('decision_type') != EXCLUSION_STATUS or not decision.get('is_current', True):
            continue
        item = catalog.get(decision.get('evidence_id'))
        if not item or decision.get('evidence_version') != current_version:
            stale.append(str(decision.get('id') or decision.get('evidence_id') or ''))
            continue
        if item['kind'] not in LEXICAL_KINDS:
            continue
        excluded.update((item['segment_index'], token) for token in item['matched_token_indexes'])
        applied.append(item['evidence_id'])
    excluded &= raw_refs
    denominator = int(report.get('coverage_denominator_tokens') or 0)
    raw_numerator = len(raw_refs)
    adjusted_numerator = max(raw_numerator - len(excluded), 0)
    adjusted_pct = round((adjusted_numerator / denominator) * 100, 1) if denominator else None
    return {
        'scoring_version': 'stage6_reviewer_adjusted_coverage_v1',
        'raw_lexical_similarity_pct': report.get('raw_lexical_similarity_pct', report.get('overall_pct')),
        'raw_coverage_tokens': raw_numerator,
        'coverage_denominator_tokens': denominator,
        'excluded_token_coverage': len(excluded),
        'reviewer_adjusted_coverage_tokens': adjusted_numerator,
        'reviewer_adjusted_similarity_pct': adjusted_pct,
        'applied_exclusion_evidence_ids': sorted(set(applied)),
        'stale_decision_ids': stale,
    }
