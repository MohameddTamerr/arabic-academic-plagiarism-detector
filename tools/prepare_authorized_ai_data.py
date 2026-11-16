"""Prepare explicitly labeled, authorized local text for research; never downloads.

Input JSON: a list of Stage 8 records with source_document_id, original text,
human-supplied provenance and explicit permissions. No labels are inferred.
Related human/AI variants must share the same source_document_id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from plagiarism_detector.ai_detection.dataset import validate_record
from plagiarism_detector.ai_detection.provenance import validate_manifest, has_arabic_content, assess_split_leakage
from tools.generate_ai_writing_splits import assign_splits


def prepare(records, manifest, seed='stage8d-v1'):
    if not isinstance(records, list) or not records:
        raise ValueError('nonempty JSON array required')
    if validate_manifest(manifest) or manifest.get('acquisition_status') != 'ACQUIRED_ISOLATED':
        raise ValueError('valid acquired manifest required')
    if manifest.get('license_permission') is not True or manifest.get('research_use_authorized') is not True:
        raise ValueError('documented research permission is required')
    if not isinstance(manifest.get('authorization_reference'), str) or not manifest['authorization_reference'].strip():
        raise ValueError('authorization reference required')
    seen = set()
    for r in records:
        if not isinstance(r, dict) or validate_record(r):
            raise ValueError('invalid provenance record')
        sid = r.get('sample_id')
        if not isinstance(sid, str) or not sid.strip() or sid in seen:
            raise ValueError('unique nonempty sample IDs required')
        seen.add(sid)
        if r.get('license_permission') is not True:
            raise ValueError('each sample must have documented permission')
        if not isinstance(r.get('source_document_id'), str) or not r['source_document_id'].strip():
            raise ValueError('source_document_id is required for every variant')
        if not isinstance(r.get('document_id'), str) or not r['document_id'].strip():
            raise ValueError('document_id required')
        if not isinstance(r.get('text'), str) or not has_arabic_content(r['text']) or '\ufffd' in r['text']:
            raise ValueError('valid Arabic Unicode text without replacement characters required')
        if not isinstance(r.get('generator_family'), str) or not r['generator_family'].strip():
            raise ValueError('explicit generator provenance required')
        if 'split' in r:
            raise ValueError('input already has split assignments; preserve the existing split instead')
        if r['provenance_label'] == 'MIXED':
            spans = r.get('segment_labels')
            if not isinstance(spans, list) or not spans:
                raise ValueError('mixed records require verified segment labels')
            previous = 0
            for span in spans:
                if not isinstance(span, dict):
                    raise ValueError('invalid mixed segment')
                start, end = span.get('start'), span.get('end')
                if (type(start) is not int or type(end) is not int or start < previous or end <= start
                    or end > len(r['text']) or span.get('label') not in ('HUMAN', 'AI_GENERATED')):
                    raise ValueError('invalid or overlapping mixed segment labels')
                previous = end
    # Connected components keep all shared source/document/author/prompt IDs together.
    assigned = assign_splits(records, seed=seed)
    if assess_split_leakage(assigned)['has_leakage']:
        raise ValueError('source metadata crosses splits')
    return assigned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seed', default='stage8d-v1')
    args = parser.parse_args()
    raw = args.input.read_bytes()
    records = json.loads(raw.decode('utf-8'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    output = prepare(records, manifest, args.seed)
    # Never overwrite a source or existing staging file.
    with args.output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'records': len(output), 'input_sha256': hashlib.sha256(raw).hexdigest(),
                      'seed': args.seed, 'status': 'prepared_not_validated'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
