from __future__ import annotations

import json
from pathlib import Path

from plagiarism_detector.citations.citation_intelligence import extract_citations, link_citations, parse_bibliography_segments

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'stage5_citation_cases.json'


def run_citation_benchmark() -> dict:
    data = json.loads(DATASET.read_text(encoding='utf-8'))
    entries = parse_bibliography_segments(data['bibliography_segments'])
    tp = fp = fn = link_correct = link_total = 0
    rows = []
    for case in data['cases']:
        citations = extract_citations(case['text'])
        links = link_citations(citations, entries)
        predicted = len(citations)
        expected = case['expected_count']
        tp += min(predicted, expected)
        fp += max(predicted - expected, 0)
        fn += max(expected - predicted, 0)
        if expected:
            link_total += 1
            link_correct += bool(links and links[0]['status'] == case['expected_link'])
        rows.append({'id': case['id'], 'citations': citations, 'links': links})
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        'dataset': data['dataset_id'], 'origin': data['origin'],
        'citation_extraction': {'tp': tp, 'fp': fp, 'fn': fn, 'precision': precision, 'recall': recall, 'f1': f1},
        'bibliography_entries_parsed': len(entries),
        'citation_link_accuracy': link_correct / link_total if link_total else None,
        'rows': rows,
    }
