#!/usr/bin/env python
"""Validate an isolated JSON/JSONL AI-writing research dataset; performs no download."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from plagiarism_detector.ai_detection.dataset import assess_dataset_readiness, validate_record
from plagiarism_detector.ai_detection.provenance import (
    find_near_duplicates, has_arabic_content, validate_manifest,
)


def _read_records(path: Path) -> list[dict]:
    raw = path.read_text(encoding='utf-8')
    if path.suffix.lower() == '.jsonl':
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError('Dataset must be a JSON array or JSONL records.')
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--near-duplicate-threshold', type=float, default=.9)
    args = parser.parse_args()
    records = _read_records(args.dataset)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    result = assess_dataset_readiness(records)
    result['manifest_errors'] = validate_manifest(manifest)
    result['non_arabic_record_ids'] = [
        str(record.get('sample_id', index)) for index, record in enumerate(records)
        if not has_arabic_content(record.get('text', ''))
    ]
    result['near_duplicate_candidates'] = find_near_duplicates(records, args.near_duplicate_threshold)
    result['invalid_record_count'] = sum(bool(validate_record(record)) for record in records)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result['manifest_errors'] and not result['invalid_records'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
