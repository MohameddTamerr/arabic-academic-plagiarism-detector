# -*- coding: utf-8 -*-
"""Dataset provenance, duplicate, and split checks for Stage 8 research.

The helpers here use only declared metadata and text fingerprints.  They are
quality gates for a proposed research corpus, not an authorship detector.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import re
import unicodedata
from urllib.parse import urlparse

MANIFEST_REQUIRED_FIELDS = {
    'dataset_id', 'title', 'version', 'publisher', 'source_url',
    'license_identifier', 'license_permission', 'acquisition_status',
}
ALLOWED_ACQUISITION_STATUSES = {
    'NOT_ACQUIRED', 'APPROVAL_REQUIRED', 'ACQUIRED_ISOLATED', 'REJECTED',
}
SPLIT_FIELDS = (
    'document_id', 'source_document_id', 'source_id', 'author_id',
    'prompt_id', 'generation_group_id', 'paraphrase_group_id',
)
ARABIC_LETTERS = re.compile(r'[\u0621-\u064A]')
WHITESPACE = re.compile(r'\s+')


def validate_manifest(manifest: dict) -> list[str]:
    """Return policy errors; an omitted term is not silently treated as allowed."""
    errors = [f'missing:{field}' for field in sorted(MANIFEST_REQUIRED_FIELDS - set(manifest))]
    if manifest.get('acquisition_status') not in ALLOWED_ACQUISITION_STATUSES:
        errors.append('invalid:acquisition_status')
    if not isinstance(manifest.get('license_permission'), bool):
        errors.append('invalid:license_permission')
    source_url = manifest.get('source_url')
    if not isinstance(source_url, str) or urlparse(source_url).scheme not in {'http', 'https'}:
        errors.append('invalid:source_url')
    if not str(manifest.get('license_identifier', '')).strip():
        errors.append('invalid:license_identifier')
    if manifest.get('acquisition_status') == 'ACQUIRED_ISOLATED' and not manifest.get('license_permission'):
        errors.append('invalid:acquired_without_permission')
    return errors


def normalize_for_duplicate_detection(text: str) -> str:
    """Conservative analysis-only normalization; raw text must remain untouched."""
    value = unicodedata.normalize('NFKC', str(text or ''))
    value = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', value)
    value = value.translate(str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي'}))
    return WHITESPACE.sub(' ', value).strip().lower()


def has_arabic_content(text: str) -> bool:
    return bool(ARABIC_LETTERS.search(str(text or '')))


def find_exact_duplicates(records: list[dict]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for index, record in enumerate(records):
        normalized = normalize_for_duplicate_detection(record.get('text', ''))
        if normalized:
            groups[sha256(normalized.encode('utf-8')).hexdigest()].append(
                str(record.get('sample_id', index))
            )
    return {fingerprint: ids for fingerprint, ids in groups.items() if len(ids) > 1}


def _token_shingles(text: str, width: int = 5) -> set[tuple[str, ...]]:
    tokens = normalize_for_duplicate_detection(text).split()
    if not tokens:
        return set()
    if len(tokens) < width:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + width]) for i in range(len(tokens) - width + 1)}


def find_near_duplicates(records: list[dict], threshold: float = 0.9) -> list[dict]:
    """Return candidate pairs with Jaccard evidence, without deleting either.

    It is intentionally a triage check: reviewers must decide whether paired
    translations, quotations, or generated variants are legitimate relations.
    """
    if not 0 < threshold <= 1:
        raise ValueError('threshold must be in (0, 1]')
    shingles = [_token_shingles(record.get('text', '')) for record in records]
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, values in enumerate(shingles):
        for shingle in values:
            postings[shingle].append(index)
    candidate_pairs: set[tuple[int, int]] = set()
    for indices in postings.values():
        for position, left in enumerate(indices):
            candidate_pairs.update((left, right) for right in indices[position + 1:])
    findings = []
    for left, right in sorted(candidate_pairs):
        union = shingles[left] | shingles[right]
        score = len(shingles[left] & shingles[right]) / len(union) if union else 0.0
        if score >= threshold:
            findings.append({
                'left_sample_id': str(records[left].get('sample_id', left)),
                'right_sample_id': str(records[right].get('sample_id', right)),
                'jaccard': round(score, 6),
            })
    return findings


def assess_split_leakage(records: list[dict]) -> dict:
    """Detect declared source/prompt groups assigned to more than one split."""
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        split = record.get('split')
        if split not in {'train', 'validation', 'test'}:
            continue
        for field in SPLIT_FIELDS:
            value = record.get(field)
            if value not in (None, ''):
                assignments[(field, str(value))].add(split)
    leaks = [
        {'field': field, 'group_id': value, 'splits': sorted(splits)}
        for (field, value), splits in sorted(assignments.items()) if len(splits) > 1
    ]
    return {'has_declared_splits': any(r.get('split') for r in records), 'has_leakage': bool(leaks), 'leaks': leaks}
