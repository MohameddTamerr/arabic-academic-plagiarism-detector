"""Read-only corpus triage; findings do not establish rights or label truth."""
from collections import Counter, defaultdict

from .dataset import validate_record
from .provenance import assess_split_leakage, find_exact_duplicates, find_near_duplicates, has_arabic_content


def audit_records(records, min_words=20):
    if min_words < 1:
        raise ValueError('min_words must be positive')
    groups = defaultdict(lambda: defaultdict(set))
    issues = defaultdict(list)
    counts = Counter()
    for i, record in enumerate(records):
        sample_id = str(record.get('sample_id', i))
        text = record.get('text')
        counts[(str(record.get('split', 'missing')), str(record.get('provenance_label', 'missing')))] += 1
        if validate_record(record):
            issues['invalid_records'].append(sample_id)
        if not isinstance(text, str) or not text.strip():
            issues['empty_text'].append(sample_id)
        elif len(text.split()) < min_words:
            issues['short_text'].append(sample_id)
        if not has_arabic_content(text):
            issues['non_arabic_text'].append(sample_id)
        if isinstance(text, str) and '\ufffd' in text:
            issues['replacement_character'].append(sample_id)
        if record.get('split') not in ('train', 'validation', 'test'):
            issues['missing_or_invalid_split'].append(sample_id)
        for field in ('topic_id', 'generator_family'):
            value = record.get(field)
            if value not in (None, '', 'NONE') and record.get('split') in ('train', 'validation', 'test'):
                groups[field][str(value)].add(record['split'])
    overlap = {field: [{'group': key, 'splits': sorted(value)} for key, value in sorted(mapping.items()) if len(value) > 1]
               for field, mapping in groups.items()}
    return {'record_count': len(records), 'minimum_words': min_words,
            'counts_by_split_and_label': [{'split': s, 'label': l, 'count': n} for (s, l), n in sorted(counts.items())],
            'issues': dict(issues), 'group_leakage': assess_split_leakage(records),
            'topic_and_generator_overlap': overlap,
            'exact_duplicate_groups': find_exact_duplicates(records),
            'near_duplicate_candidates': find_near_duplicates(records),
            'caveat': 'Triage only; check rights, labels, near duplicates, domain and absent group metadata manually.'}
