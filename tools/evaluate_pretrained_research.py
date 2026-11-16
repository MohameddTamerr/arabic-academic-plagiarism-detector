"""Evaluate a trusted local Hamed-format detector on an authorized JSON dataset.

No model/dataset downloads. This tool does not certify data independence,
permission, model provenance, label mapping or scientific validity.
"""
import argparse
import hashlib
import json
from pathlib import Path

from plagiarism_detector.ai_detection.pretrained_research import HamedResearchAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--checkpoint-sha256', required=True)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--class-one', choices=['HUMAN', 'AI_GENERATED'], required=True)
    parser.add_argument('--label-mapping-evidence', required=True)
    parser.add_argument('--preprocessing', choices=['original', 'repository_dediacritized'], required=True)
    parser.add_argument('--ai-threshold', type=float, required=True, help='fix using separate validation data, never tune on this dataset')
    parser.add_argument('--batch-size', type=int, default=4)
    args = parser.parse_args()
    if not 0 <= args.ai_threshold <= 1:
        parser.error('ai-threshold must be between 0 and 1')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    if not all(manifest.get(k) is True for k in ('dataset_use_authorized', 'model_use_authorized', 'independent_evaluation_attested')):
        raise ValueError('documented model/dataset use and independent evaluation attestations required')
    if not all(isinstance(manifest.get(k), str) and manifest[k].strip() for k in ('dataset_authorization_reference', 'model_authorization_reference')):
        raise ValueError('authorization references required')
    raw = args.data.read_bytes()
    records = json.loads(raw.decode('utf-8'))
    if not isinstance(records, list) or not records:
        raise ValueError('non-empty JSON array required')
    if any(not isinstance(r, dict) or r.get('provenance_label') not in ('HUMAN', 'AI_GENERATED') or not isinstance(r.get('text'), str) or not r['text'].strip() for r in records):
        raise ValueError('every record must have original text and an independently verified binary provenance label')
    y = [int(r['provenance_label'] == 'AI_GENERATED') for r in records]
    if set(y) != {0, 1}:
        raise ValueError('evaluation requires both classes')
    mapping = {1: args.class_one, 0: 'HUMAN' if args.class_one == 'AI_GENERATED' else 'AI_GENERATED'}
    model = HamedResearchAdapter(args.model_dir, args.checkpoint, checkpoint_sha256=args.checkpoint_sha256,
        label_mapping=mapping, label_mapping_evidence=args.label_mapping_evidence,
        preprocessing=args.preprocessing, batch_size=args.batch_size)
    result = model.analyze([{'paragraph_id': r.get('sample_id'), 'page_number': r.get('page_number'), 'text': r['text']} for r in records])
    scores = [r['class_1_score'] if args.class_one == 'AI_GENERATED' else 1-r['class_1_score'] for r in result]
    predictions = [int(p >= args.ai_threshold) for p in scores]
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, brier_score_loss
    tn, fp, fn, tp = (int(x) for x in confusion_matrix(y, predictions, labels=[0, 1]).ravel())
    report = {'research_only': True, 'data_sha256': hashlib.sha256(raw).hexdigest(), 'checkpoint_sha256': args.checkpoint_sha256,
        'preprocessing': args.preprocessing, 'class_one': args.class_one, 'count': len(y), 'truncated_count': sum(r['truncated'] for r in result),
        'ai_threshold': args.ai_threshold, 'accuracy': accuracy_score(y, predictions), 'precision': precision_score(y, predictions, zero_division=0),
        'recall': recall_score(y, predictions, zero_division=0), 'f1': f1_score(y, predictions, zero_division=0),
        'fpr': fp / (fp + tn), 'fnr': fn / (fn + tp), 'confusion_matrix': [[tn, fp], [fn, tp]],
        'brier_score_uncalibrated': brier_score_loss(y, scores)}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
