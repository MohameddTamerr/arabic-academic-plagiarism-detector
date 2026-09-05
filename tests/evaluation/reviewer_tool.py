# -*- coding: utf-8 -*-
"""
أداة مراجعة العينات والتحكيم المزدوج المستقل (Offline Human Reviewer & Double-Review Tool):
- تتيح للمحكمين والخبراء مراجعة تصنيفات العينات مع درجات الثقة (Confidence Level).
- تدعم التحكيم المستقل المزدوج (Double-Review) مع طابور فض النزاعات (ADJUDICATION_REQUIRED).
- تدعم تسجيل حالات السلبيات الزائفة والمصادر المفقودة (Missed Source / False Negative Discovery).
- تحفظ المراجعات محلياً في reviewer_labels.json وسجل المصادر المفقودة في missed_sources.jsonl.
"""

import sys
import io
import json
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_DATASET_FILE = _HERE / 'dataset.json'
_LABELS_FILE = _HERE / 'reviewer_labels.json'
_MISSED_SOURCES_LOG = _HERE / 'missed_sources.jsonl'

VALID_ACADEMIC_CLASSES = {
    'EXACT_COPY',
    'MODIFIED_COPY',
    'PARAPHRASE',
    'PROPERLY_CITED',
    'COMMON_TEXT',
    'ORIGINAL',
    'UNCERTAIN'
}

VALID_DECISIONS = {
    'correct',
    'false_positive',
    'false_negative',
    'uncertain',
    'needs_further_review'
}

VALID_FAILURE_CATEGORIES = {
    'retrieval_failure',
    'matcher_failure',
    'segmentation_failure',
    'ocr_failure',
    'citation_classification_issue',
    'common_text_suppression_issue',
    'semantic_paraphrase_limitation',
    'reference_absent_from_corpus',
    'other'
}


def load_dataset() -> list:
    if not _DATASET_FILE.exists():
        return []
    with open(_DATASET_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_reviews() -> dict:
    if not _LABELS_FILE.exists():
        return {}
    with open(_LABELS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_reviews(reviews: dict):
    with open(_LABELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)


def add_review(
    sample_id: str,
    reviewer_id: str,
    decision: str,
    class_label: Optional[str] = None,
    confidence: float = 1.0,
    notes: str = ''
) -> bool:
    """إضافة مراجعة محكم مع دعم التحكيم المزدوج وكشف تضارب القرارات."""
    dec_clean = decision.lower()
    if dec_clean not in VALID_DECISIONS:
        print(f"خطأ: القرار '{decision}' غير صالح.")
        return False

    if class_label:
        cls_upper = class_label.upper()
        if cls_upper not in VALID_ACADEMIC_CLASSES:
            print(f"خطأ: الصنف '{class_label}' غير صالح.")
            return False
    else:
        cls_upper = None

    dataset = load_dataset()
    sample = next((s for s in dataset if s['sample_id'] == sample_id), None)
    if not sample:
        print(f"خطأ: لم يتم العثور على العينة '{sample_id}'")
        return False

    reviews = load_reviews()
    entry = reviews.get(sample_id, {
        'sample_id': sample_id,
        'original_class': sample.get('expected_class') or sample.get('expected_category', 'UNKNOWN'),
        'reviews': [],
        'status': 'PENDING_DOUBLE_REVIEW',
        'final_class': None,
        'final_decision': None
    })

    # إضافة مراجعة المحكم الجديد
    rev_record = {
        'reviewer_id': reviewer_id,
        'decision': dec_clean,
        'confirmed_class': cls_upper or entry['original_class'],
        'confidence': float(confidence),
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'notes': notes
    }

    # استبدال المراجعة السابقة لنفس المحكم إن وجدت
    entry['reviews'] = [r for r in entry['reviews'] if r['reviewer_id'] != reviewer_id]
    entry['reviews'].append(rev_record)

    # التحقق من حالة المراجعة المزدوجة
    if len(entry['reviews']) == 1:
        entry['status'] = 'SINGLE_REVIEWED'
        entry['final_class'] = entry['reviews'][0]['confirmed_class']
        entry['final_decision'] = entry['reviews'][0]['decision']
    elif len(entry['reviews']) >= 2:
        # مقارنة قرارات المحكمين
        r1, r2 = entry['reviews'][0], entry['reviews'][1]
        if r1['confirmed_class'] == r2['confirmed_class'] and r1['decision'] == r2['decision']:
            entry['status'] = 'CONFIRMED'
            entry['final_class'] = r1['confirmed_class']
            entry['final_decision'] = r1['decision']
        else:
            entry['status'] = 'ADJUDICATION_REQUIRED'
            entry['final_class'] = None
            entry['final_decision'] = None

    entry['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reviews[sample_id] = entry
    save_reviews(reviews)
    print(f"✅ تم تسجيل مراجعة [{reviewer_id}] للعينة [{sample_id}] -> الحالة: {entry['status']}")
    return True


def adjudicate_sample(
    sample_id: str,
    adjudicator_id: str,
    final_decision: str,
    final_class: str,
    notes: str = ''
) -> bool:
    """فض النزاع وتثبيت القرار النهائي للجنة التحكيم العليا."""
    dec_clean = final_decision.lower()
    cls_upper = final_class.upper()

    if dec_clean not in VALID_DECISIONS or cls_upper not in VALID_ACADEMIC_CLASSES:
        print("خطأ: القرار أو الصنف النهائي غير صالح.")
        return False

    reviews = load_reviews()
    if sample_id not in reviews:
        print(f"خطأ: العينة '{sample_id}' غير مسجلة في المراجعات.")
        return False

    entry = reviews[sample_id]
    entry['status'] = 'ADJUDICATED'
    entry['final_class'] = cls_upper
    entry['final_decision'] = dec_clean
    entry['adjudication'] = {
        'adjudicator_id': adjudicator_id,
        'final_decision': dec_clean,
        'final_class': cls_upper,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'notes': notes
    }
    entry['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reviews[sample_id] = entry
    save_reviews(reviews)
    print(f"✅ تم فض النزاع وتثبيت القرار النهائي للعينة [{sample_id}] كـ [{cls_upper} / {dec_clean}]")
    return True


def log_missed_source(
    query_span: str,
    expected_source: str,
    existed_in_corpus: bool,
    matcher_score: float = 0.0,
    failure_category: str = 'retrieval_failure',
    notes: str = ''
) -> Dict[str, Any]:
    """تسجيل حالات السلبيات الزائفة والمصادر المفقودة التي اكتشفها المحكمون."""
    if failure_category not in VALID_FAILURE_CATEGORIES:
        raise ValueError(f"Invalid failure category '{failure_category}'. Must be one of: {sorted(VALID_FAILURE_CATEGORIES)}")

    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "query_span": query_span.strip(),
        "expected_source": expected_source.strip(),
        "existed_in_corpus": bool(existed_in_corpus),
        "matcher_score": float(matcher_score),
        "failure_category": failure_category,
        "notes": notes.strip()
    }

    with open(_MISSED_SOURCES_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
