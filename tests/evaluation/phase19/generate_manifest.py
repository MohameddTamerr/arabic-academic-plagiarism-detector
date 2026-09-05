# -*- coding: utf-8 -*-
"""
توليد بيان الإصدار المؤسسي الرسمي (Release Manifest Generator):
- يحسب بصمات التجزئة SHA-256 للملفات الحرجة والخدمات الأساسية.
- يسجل إعدادات الإنتاج الفعلية، ومحددات البيئة، وقرار الجاهزية الرسمي.
- يحفظ الملف في release_manifest.json ضمن جذر المشروع.
"""

import os
import json
import time
import hashlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

CRITICAL_FILES = [
    "config.py",
    "app/__init__.py",
    "app/versioning.py",
    "app/services/job_queue_service.py",
    "app/services/scan_service.py",
    "app/services/report_integrity_service.py",
    "app/services/backup_service.py",
    "app/services/system_health_service.py",
    "app/services/corpus_governance_service.py",
    "plagiarism_detector/reporting/report_builder.py",
    "plagiarism_detector/detection/shingle_matcher.py",
    "plagiarism_detector/detection/tfidf_matcher.py",
    "plagiarism_detector/detection/candidate_retriever.py",
    "plagiarism_detector/citations/citation_detector.py"
]


def generate_manifest() -> dict:
    hashes = {}
    for rel_path in CRITICAL_FILES:
        full_path = _ROOT / rel_path
        if full_path.exists():
            h = hashlib.sha256(full_path.read_bytes()).hexdigest()
            hashes[rel_path] = h
        else:
            hashes[rel_path] = "FILE_NOT_FOUND"

    manifest = {
        "release_version": "v1.0.0-rc1",
        "build_timestamp": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        "application_name": "Arabic Academic Plagiarism Detector",
        "application_version": "2.4.0",
        "engine_version": "1.2.0",
        "database_schema_version": "1.0.0",
        "report_schema_version": "1.0",
        "detector_profile": "LIGHT (Jaccard + TF-IDF)",
        "production_settings": {
            "shingle_size": 5,
            "jaccard_threshold": 0.40,
            "tfidf_threshold": 0.40,
            "semantic_threshold": 0.70,
            "max_candidate_retrieval": 50,
            "enable_semantic_model": False,
            "enable_ocr": True,
            "max_concurrent_scans": 2,
            "max_concurrent_ocr_jobs": 1
        },
        "phase19_proposals_status": {
            "EXP-01_dual_channel_retrieval": "NOT DEPLOYED (Accepted candidate, deferred to post-pilot release)",
            "EXP-02_morphological_char_paraphrase": "REJECTED (High false positive rate on domain hard negatives)",
            "EXP-03_common_text_span_filtering": "NOT DEPLOYED (Accepted candidate, deferred to post-pilot release)",
            "EXP-04_citation_refinement": "NOT DEPLOYED (Accepted candidate, deferred to post-pilot release)",
            "EXP-05_semantic_fail_closed": "CONFIRMED_BASELINE (Active in production fallback)",
            "EXP-06_segment_length_guard": "CONFIRMED_BASELINE (Active in production segmenter)",
            "EXP-07_shingle_k5_confirmation": "CONFIRMED_BASELINE (Active in production settings)"
        },
        "optional_components": {
            "semantic_model": "UNAVAILABLE (Air-gapped safe fail-closed without network requests)",
            "ocr_tesseract": "OPTIONAL (Process-isolated with cross-process lock when Tesseract installed)"
        },
        "validation_scope": {
            "DEVELOPER_SYNTHETIC": 323,
            "DEVELOPER_SYNTHETIC_HOLDOUT": 11,
            "EXPERT_REVIEWED": 0,
            "REAL_ANONYMIZED": 0,
            "disclaimer": "Internal synthetic evaluation only; no institutional or ministry-wide accuracy claim."
        },
        "readiness_verdict": "READY FOR CONTROLLED PILOT WITH MANDATORY CONDITIONS",
        "mandatory_conditions": [
            "1. Decision-support only: The detector assists human reviewers; automated academic accusations or disciplinary rejections are strictly prohibited.",
            "2. Single-node institutional deployment: Maximum 2 concurrent active scans; SQLite DB size <= 10GB; reference corpus <= 50,000 items.",
            "3. Strict air-gapped zero-network isolation on local LAN or standalone workstation with zero external WAN connectivity.",
            "4. Post-pilot calibration: The pilot must be used to collect and expert-review >= 100 real anonymized samples via reviewer_tool.py before wider deployment."
        ],
        "critical_file_hashes_sha256": hashes
    }

    out_file = _ROOT / "release_manifest.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Manifest saved to: {out_file}")
    return manifest


if __name__ == "__main__":
    generate_manifest()
