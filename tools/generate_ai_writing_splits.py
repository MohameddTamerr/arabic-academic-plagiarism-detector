#!/usr/bin/env python
"""Create deterministic group-disjoint splits for an already authorized dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from plagiarism_detector.ai_detection.provenance import SPLIT_FIELDS, assess_split_leakage


def _read(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, list):
        raise ValueError('Input must be a JSON array.')
    return value


def _group_key(record: dict) -> str:
    values = [f'{field}:{record[field]}' for field in SPLIT_FIELDS if record.get(field) not in (None, '')]
    if not values:
        return f"sample:{record.get('sample_id')}"
    return '|'.join(values)


def assign_splits(records: list[dict], seed: str = 'stage8b-v1') -> list[dict]:
    """Hash connected metadata groups so no declared identifier crosses a split."""
    parent = list(range(len(records)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    seen = {}
    for index, record in enumerate(records):
        for field in SPLIT_FIELDS:
            value = record.get(field)
            if value not in (None, ''):
                key = (field, str(value))
                if key in seen:
                    union(index, seen[key])
                else:
                    seen[key] = index

    components = {}
    for index, record in enumerate(records):
        components.setdefault(find(index), []).append(index)
    output = [None] * len(records)
    for indices in components.values():
        group = '|'.join(sorted(_group_key(records[index]) for index in indices))
        digest = int(hashlib.sha256(f'{seed}:{group}'.encode('utf-8')).hexdigest()[:8], 16) % 100
        split = 'train' if digest < 70 else 'validation' if digest < 85 else 'test'
        for index in indices:
            output[index] = {**records[index], 'split': split}
    leakage = assess_split_leakage(output)
    if leakage['has_leakage']:
        raise ValueError(f"group metadata connects proposed splits: {leakage['leaks']}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seed', default='stage8b-v1')
    args = parser.parse_args()
    args.output.write_text(json.dumps(assign_splits(_read(args.input), args.seed), ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
