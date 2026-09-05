# -*- coding: utf-8 -*-
"""
أداة استيراد العينات الأكاديمية الحقيقية مع إلغاء الهوية والتعمية المحصنة (Hardened Offline Anonymized Ingest Tool):
- تتيح إدخال نصوص أكاديمية حقيقية للتقييم مع حذف صارم لكافة البيانات التعريفية والشخصية (PII).
- تعمل محلياً بنسبة 100% دون أي اتصال خارجي بالإنترنت (Strictly Offline / Air-Gapped).
- تعمية أسماء الباحثين، المشرفين، الجامعات، أرقام الهوية، الأرقام الجامعية، الهواتف، البريد، ومسارات الملفات.
- توليد معرفات عشوائية مجهولة ومستقرة عبر تجزئة SHA-256.
"""

import os
import re
import sys
import io
import json
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_ANONYMIZED_DIR = _HERE / "anonymized_data"
_AUDIT_LOG = _ANONYMIZED_DIR / "ingest_audit.jsonl"

_EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
_PHONE_REGEX = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
_NATIONAL_ID_REGEX = re.compile(r'\b[12]\d{9,13}\b')
_STUDENT_ID_REGEX = re.compile(r'(?:رقم\s+جامعي|الرقم\s+الأكاديمي|الرقم\s+الجامعي|student\s*id)\s*[:=]?\s*[\dA-Za-z\-]+', re.IGNORECASE)
_FILE_PATH_REGEX = re.compile(r'(?:[A-Za-z]\:[\\\/][\w\d_\\\/\.\-]+|\/(?:home|var|tmp|Users|app)[\w\d_\/\.\-]+)')

_ACADEMIC_TITLE_PREFIXES = re.compile(
    r'(?:الدكتور|الدكتورة|الأستاذ الدكتور|الأستاذة الدكتورة|أ\.د\.|د\.|الباحث|الباحثة|الطالب|الطالبة|المؤلف|المؤلفة|المشرف|إشراف|إعداد|المحكم|رئيس اللجنة|المقدم من|تقديم|إعداد الطالب|إعداد الباحث)\s+[\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){1,3}',
    re.IGNORECASE
)
_INSTITUTION_REGEX = re.compile(
    r'(?:جامعة|كلية|قسم|معهد|أكاديمية|مركز بحوث|عمادة الدراسات العليا|جامعة نايف العربية للعلوم الأمنية)\s+[\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+){1,4}',
    re.IGNORECASE
)


def sanitize_text(text: str) -> str:
    """إزالة وتعمية كافة البيانات الشخصية والمسارات التعريفية."""
    if not text:
        return ""
    sanitized = _EMAIL_REGEX.sub("[EMAIL_REDACTED]", text)
    sanitized = _PHONE_REGEX.sub("[PHONE_REDACTED]", sanitized)
    sanitized = _STUDENT_ID_REGEX.sub("[STUDENT_ID_REDACTED]", sanitized)
    sanitized = _NATIONAL_ID_REGEX.sub("[ID_NUM_REDACTED]", sanitized)
    sanitized = _FILE_PATH_REGEX.sub("[PATH_REDACTED]", sanitized)
    sanitized = _ACADEMIC_TITLE_PREFIXES.sub("[PERSON_NAME_REDACTED]", sanitized)
    sanitized = _INSTITUTION_REGEX.sub("[INSTITUTION_REDACTED]", sanitized)
    return sanitized.strip()


def generate_anonymous_id(content: str, domain: str) -> str:
    """توليد معرف عشوائي ثابت غير قابل للعكس للعينات المعماة."""
    h = hashlib.sha256((content + domain).encode('utf-8')).hexdigest()[:12]
    return f"ANON_{domain.upper()[:3]}_{h}"


def ingest_sample(
    suspicious_text: str,
    source_text: str,
    domain: str = "general",
    category: str = "MODIFIED_COPY",
    reviewer_notes: str = "",
    allow_empty_source: bool = False
) -> Dict[str, Any]:
    """إدخال وتعمية وتخزين عينة أكاديمية حقيقية محلياً."""
    valid_categories = {"EXACT_COPY", "MODIFIED_COPY", "PARAPHRASE", "PROPERLY_CITED", "COMMON_TEXT", "ORIGINAL"}
    cat_upper = category.upper()
    if cat_upper not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {sorted(valid_categories)}")

    _ANONYMIZED_DIR.mkdir(parents=True, exist_ok=True)

    sanitized_suspicious = sanitize_text(suspicious_text)
    sanitized_source = sanitize_text(source_text) if source_text else ""

    if not sanitized_suspicious:
        raise ValueError("Suspicious text cannot be empty.")
    if not sanitized_source and not allow_empty_source and cat_upper != "ORIGINAL":
        raise ValueError("Source text cannot be empty for plagiarism evaluation classes.")

    sample_id = generate_anonymous_id(sanitized_suspicious, domain)

    record = {
        "sample_id": sample_id,
        "domain": domain,
        "expected_class": cat_upper,
        "generation_origin": "REAL_ANONYMIZED",
        "suspicious_text": sanitized_suspicious,
        "source_text": sanitized_source,
        "suspicious_len_chars": len(sanitized_suspicious),
        "source_len_chars": len(sanitized_source),
        "ingest_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reviewer_notes": reviewer_notes,
        "pii_redacted": True
    }

    sample_path = _ANONYMIZED_DIR / f"{sample_id}.json"
    with open(sample_path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    audit_entry = {
        "sample_id": sample_id,
        "domain": domain,
        "expected_class": cat_upper,
        "origin": "REAL_ANONYMIZED",
        "timestamp": record["ingest_timestamp"],
        "suspicious_chars": len(sanitized_suspicious),
        "source_chars": len(sanitized_source)
    }
    with open(_AUDIT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

    return record


def list_anonymized_samples() -> List[Dict[str, Any]]:
    """استعراض كافة العينات المعماة المخزنة محلياً."""
    if not _ANONYMIZED_DIR.exists():
        return []
    samples = []
    for f in _ANONYMIZED_DIR.glob("ANON_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                samples.append(json.load(fp))
        except Exception:
            pass
    return samples
