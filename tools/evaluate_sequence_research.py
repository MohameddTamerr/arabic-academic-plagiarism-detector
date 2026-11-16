"""Evaluate one local sequence classifier against an authorized Stage 8 test split."""

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform

from plagiarism_detector.ai_detection.dataset import validate_record
from plagiarism_detector.ai_detection.provenance import (
    assess_split_leakage, find_exact_duplicates, has_arabic_content,
)
from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter, SequenceResearchError


def select_test_records(records, manifest, data_sha256):
    if not isinstance(manifest, dict) or not all(manifest.get(key) is True for key in (
        'dataset_use_authorized', 'model_use_authorized', 'independent_evaluation_attested',
    )):
        raise ValueError('Documented use and independent-evaluation attestations are required.')
    for key in ('dataset_authorization_reference', 'model_authorization_reference', 'threshold_reference'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f'A documented {key} is required.')
    if manifest.get('data_sha256') != data_sha256:
        raise ValueError('Evaluation data do not match the authorization manifest hash.')
    low, high = manifest.get('human_threshold'), manifest.get('ai_threshold')
    if type(low) not in (int, float) or type(high) not in (int, float) or not 0 <= low < high <= 1:
        raise ValueError('Expected predeclared human and AI thresholds with a range for abstention.')

    if not isinstance(records, list) or not records:
        raise ValueError('A nonempty array of Stage 8 records is required.')
    identifiers = set()
    labels = Counter()
    test_records = []
    for record in records:
        if not isinstance(record, dict) or validate_record(record) or record['license_permission'] is not True:
            raise ValueError('Every record needs valid provenance and recorded permission.')
        for key in ('sample_id', 'document_id', 'source_document_id', 'data_origin'):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f'Expected a nonempty {key} for every sample.')
        sample_id = record['sample_id']
        if sample_id in identifiers or record.get('split') not in ('train', 'validation', 'test'):
            raise ValueError('Each sample needs a unique ID and a declared split.')
        identifiers.add(sample_id)
        text = record['text']
        if not isinstance(text, str) or not has_arabic_content(text) or '\ufffd' in text:
            raise ValueError('Expected original Arabic text without replacement characters.')
        if record['split'] == 'test':
            if 'SYNTHETIC' in record['data_origin'].upper():
                raise ValueError('Synthetic fixtures are ineligible for the evaluation test split.')
            label = record['provenance_label']
            labels[label] += 1
            if label in ('HUMAN', 'AI_GENERATED'):
                test_records.append(record)

    if assess_split_leakage(records)['has_leakage'] or find_exact_duplicates(records):
        raise ValueError('Duplicate text or source metadata crosses or compromises evaluation splits.')
    if not labels['HUMAN'] or not labels['AI_GENERATED']:
        raise ValueError('The test split needs both independently labeled binary classes.')
    return test_records, dict(labels)


def evaluate(adapter, records, human_threshold, ai_threshold):
    classes = ('HUMAN', 'AI_GENERATED')
    table = {label: dict.fromkeys((*classes, 'abstained'), 0) for label in classes}
    reasons = Counter()
    for start in range(0, len(records), adapter.batch_size):
        batch = records[start:start + adapter.batch_size]
        results = adapter.analyze(batch)
        for record, result in zip(batch, results, strict=True):
            decision = 'abstained'
            if result['truncated']:
                reasons['truncated'] += 1
            elif result['scores'] is None:
                reasons[result['reason']] += 1
            else:
                value = result['scores']['AI_GENERATED']
                if value >= ai_threshold:
                    decision = 'AI_GENERATED'
                elif value <= human_threshold:
                    decision = 'HUMAN'
                else:
                    reasons['between_thresholds'] += 1
            table[record['provenance_label']][decision] += 1

    human, ai = (table[label] for label in classes)
    tn, fp, fn, tp = human['HUMAN'], human['AI_GENERATED'], ai['HUMAN'], ai['AI_GENERATED']
    classified = tn + fp + fn + tp
    return {
        'confusion_counts': table,
        'abstention_reasons': dict(reasons),
        'classified_coverage': classified / len(records),
        'coverage_by_label': {label: (counts['HUMAN'] + counts['AI_GENERATED']) / sum(counts.values())
                              for label, counts in table.items()},
        'accuracy_among_classified': (tn + tp) / classified if classified else None,
        'false_positive_rate_all_human': fp / sum(human.values()),
        'false_positive_rate_classified_human': fp / (tn + fp) if tn + fp else None,
        'false_negative_rate_all_ai': fn / sum(ai.values()),
        'false_negative_rate_classified_ai': fn / (fn + tp) if fn + tp else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--file-hashes', type=Path, required=True)
    parser.add_argument('--class-one', choices=['HUMAN', 'AI_GENERATED'], required=True)
    parser.add_argument('--mapping-evidence', required=True)
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--artifact-mode', choices=['fp32', 'int8'])
    parser.add_argument('--artifact-manifest-sha256')
    parser.add_argument('--threads', choices=[1, 2, 4], type=int, default=2)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists.')
    artifact_options = (args.artifact, args.artifact_mode, args.artifact_manifest_sha256)
    if any(artifact_options) and not all(artifact_options):
        parser.error('Provide all three artifact options for TorchScript.')

    raw = args.data.read_bytes()
    manifest_bytes = args.manifest.read_bytes()
    data_hash = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(manifest_bytes)
    records, counts = select_test_records(json.loads(raw), manifest, data_hash)
    del raw
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    import torch

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    adapter = SequenceResearchAdapter(
        args.model_dir, file_hashes=json.loads(args.file_hashes.read_bytes()),
        label_mapping={1: args.class_one, 0: 'AI_GENERATED' if args.class_one == 'HUMAN' else 'HUMAN'},
        mapping_evidence=args.mapping_evidence, batch_size=args.batch_size,
        scripted_artifact=args.artifact, scripted_mode=args.artifact_mode,
        scripted_manifest_sha256=args.artifact_manifest_sha256,
    )
    try:
        metrics = evaluate(adapter, records, manifest['human_threshold'], manifest['ai_threshold'])
        report = {
            'research_only': True,
            'scientific_validation_status': 'not_validated',
            'data_sha256': data_hash,
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'test_counts_by_provenance': counts,
            'eligible_binary_samples': len(records),
            'human_threshold': manifest['human_threshold'],
            'ai_threshold': manifest['ai_threshold'],
            'model': adapter.provenance(),
            'runtime': {'platform': platform.platform(), 'python': platform.python_version(),
                        'threads': args.threads, **{name: version(name) for name in
                                                   ('torch', 'transformers', 'tokenizers')}},
            'metrics': metrics,
        }
    except SequenceResearchError as exc:
        parser.exit(2, f'Evaluation failed: {exc}\n')
    finally:
        adapter.close()

    with args.output.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
