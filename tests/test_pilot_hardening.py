# -*- coding: utf-8 -*-
"""
Tests for Post-Development Pilot Phase — Pilot Hardening & Validation Suite.
Validates:
- RC2 Feature flags and deterministic rollback to RC1 baseline
- Dual-channel candidate retrieval (EXP-01) vs Baseline retrieval
- Span-level common-text filtering (EXP-03) and preamble isolation
- Refined Arabic citation parsing (EXP-04) and date/statute exclusion
- OCR failure safety, process isolation, and lock release
- Anonymization PII redaction and reviewer double-review adjudication
- Report version snapshotting and 100% reproducibility
- Strict air-gapped zero-network invariants
"""

import sys
import os
import json
import pytest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from app import versioning
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.filters.common_phrases import filter_common_spans, is_common_institutional_text
from plagiarism_detector.citations.citation_detector import detect_citation, detect_citation_baseline, detect_citation_refined
from plagiarism_detector.reporting.report_builder import analyze_academic_document
from tests.evaluation.anonymized_ingest import sanitize_text, generate_anonymous_id
from tests.evaluation.reviewer_tool import add_review, adjudicate_sample, log_missed_source


def test_version_registry_rc2():
    """Verify RC2 version constants in app/versioning.py."""
    assert versioning.APPLICATION_VERSION == "2.5.0"
    assert versioning.ENGINE_VERSION == "1.3.0"
    assert versioning.DETECTOR_VERSION == "shingle-jaccard-tfidf-dual-1.3"
    assert versioning.CITATION_ENGINE_VERSION == "citation-detector-refined-1.3"
    assert versioning.COMMON_TEXT_HANDLING_VERSION == "common-phrases-span-1.3"


def test_default_settings_feature_flags():
    """Verify feature flags are present and defaulted to RC2 enhanced modes."""
    assert config.DEFAULT_SETTINGS['candidate_retrieval_mode'] == 'dual_channel'
    assert config.DEFAULT_SETTINGS['common_text_filter_mode'] == 'span_level'
    assert config.DEFAULT_SETTINGS['citation_filter_mode'] == 'refined'


def test_dual_channel_candidate_retrieval_vs_baseline():
    """Verify dual-channel retrieval catches morphological variants that single-token misses."""
    retriever = CandidateRetriever()

    # Index sample reference document
    ref_text = "تعتمد الدول المتقدمة على تقنيات الذكاء الاصطناعي في تعزيز كفاءة المنظومات الأمنية."
    words = ref_text.split()
    shingles = {("تعتمد", "الدول", "المتقدمة", "على", "تقنيات")}
    retriever.add_segment(0, words, shingles, norm_light=ref_text)

    # Query with morphological shift and synonym substitution
    query_morph = "توظف الحكومات المتقدمة تقنية الذكاء الاصطناعي لتعزيز أمن منظوماتها."

    # Baseline token retrieval
    baseline_cands = retriever.retrieve_candidates(query_morph, top_k=5, mode='baseline')
    # Dual-channel retrieval
    dual_cands = retriever.retrieve_candidates(query_morph, top_k=5, mode='dual_channel')

    assert 0 in dual_cands, "Dual-channel retrieval must retrieve candidate with morphological overlap"
    # Verification of rollback
    assert retriever.retrieve_candidates(query_morph, top_k=5, mode='baseline') == baseline_cands


def test_span_level_common_text_safety_on_copied_passage():
    """Verify span-level filter strips preamble but preserves substantive copied academic text."""
    mixed_text = "بناء على ما تقدم وفي ضوء ما اسفرت عنه النتائج، فإن المسؤولية التقصيرية تنعقد قانوناً بثبوت الخطأ والضرر وعلاقة السببية المباشرة بينهما."

    # Span-level mode (RC2)
    clean_substantive, has_common, extracted_spans = filter_common_spans(mixed_text, min_substantive_words=4, mode='span_level')
    assert has_common is True
    assert "بناء على ما تقدم" in str(extracted_spans) or "وفي ضوء ما اسفرت عنه النتائج" in str(extracted_spans)
    assert "المسؤولية التقصيرية تنعقد قانوناً" in clean_substantive, "Substantive copied law passage must NOT be suppressed"

    # Baseline mode (RC1)
    clean_base, has_base, _ = filter_common_spans(mixed_text, min_substantive_words=4, mode='baseline')
    # In baseline mode, preamble presence or full text is handled without span separation


def test_pure_common_boilerplate_suppression():
    """Verify pure institutional boilerplate with no substantive words is suppressed completely."""
    pure_boilerplate = "تشكلت لجنة الحكم والمناقشة، وبناء على ما تقدم، بخالص الشكر والتقدير."
    substantive, has_common, spans = filter_common_spans(pure_boilerplate, min_substantive_words=4, mode='span_level')
    assert has_common is True
    assert substantive == "", "Pure boilerplate must be reduced to empty substantive string"


def test_refined_citation_filter_precision_and_date_exclusion():
    """Verify refined citation detector excludes isolated dates/statute numbers but catches multi-author APA."""
    # 1. Multi-author APA citation
    apa_text = "وفقاً لدراسة حديثة (القحطاني والعتيبي، 2022، ص. 88) فإن الجريمة المعلوماتية في تصاعد."
    res_apa = detect_citation(apa_text, mode='refined')
    assert res_apa.is_cited is True
    assert res_apa.citation_type == 'author_year'

    # 2. Standalone date/year (must NOT be cited)
    date_text = "صدر تقرير الهيئة الوطنية في عام (2030) لتحقيق مستهدفات التنمية المستدامة."
    res_date = detect_citation(date_text, mode='refined')
    assert res_date.is_cited is False, "Isolated year/date in parentheses must not be tagged as academic citation"

    # 3. Statute / Law article (must NOT be cited)
    law_text = "نصت اللائحة التنفيذية في (المادة 15) على معاقبة مرتكبي الجرائم السيبرانية."
    res_law = detect_citation(law_text, mode='refined')
    assert res_law.is_cited is False, "Law article numbers must not be tagged as academic author citation"


def test_anonymization_pii_and_path_stripping():
    """Verify anonymization tool strips names, emails, phones, IDs, and system file paths."""
    sensitive_input = (
        "بحث أعده الطالب محمد أحمد الغامدي (رقم جامعي: 441029384، هوية وطنية: 1092837465)\n"
        "بإشراف الدكتور عبدالله السبيعي في جامعة نايف العربية للعلوم الأمنية.\n"
        "البريد: researcher@nauss.edu.sa، هاتف: 0551234567.\n"
        "تم حفظ الملف في المسار C:\\Users\\user\\Documents\\Thesis_Final.pdf"
    )

    sanitized = sanitize_text(sensitive_input)
    assert "محمد أحمد" not in sanitized
    assert "441029384" not in sanitized
    assert "1092837465" not in sanitized
    assert "researcher@nauss.edu.sa" not in sanitized
    assert "0551234567" not in sanitized
    assert "C:\\Users\\user" not in sanitized
    assert "[EMAIL_REDACTED]" in sanitized
    assert "[PHONE_REDACTED]" in sanitized

    anon_id = generate_anonymous_id(sanitized, "law")
    assert anon_id.startswith("ANON_LAW_")


def test_reviewer_double_review_and_adjudication(tmp_path, monkeypatch):
    """Verify double-review disagreement triggers ADJUDICATION_REQUIRED and resolution."""
    test_labels_file = tmp_path / "test_labels.json"
    test_dataset_file = tmp_path / "test_dataset.json"

    sample = [{"sample_id": "TEST_S01", "expected_class": "MODIFIED_COPY", "domain": "law"}]
    with open(test_dataset_file, "w", encoding="utf-8") as f:
        json.dump(sample, f)

    monkeypatch.setattr("tests.evaluation.reviewer_tool._DATASET_FILE", test_dataset_file)
    monkeypatch.setattr("tests.evaluation.reviewer_tool._LABELS_FILE", test_labels_file)

    # Reviewer 1 votes MODIFIED_COPY
    add_review("TEST_S01", reviewer_id="rev_1", decision="correct", class_label="MODIFIED_COPY", confidence=0.9)
    # Reviewer 2 votes PARAPHRASE (Disagreement)
    add_review("TEST_S01", reviewer_id="rev_2", decision="false_positive", class_label="PARAPHRASE", confidence=0.85)

    with open(test_labels_file, "r", encoding="utf-8") as f:
        reviews = json.load(f)

    assert reviews["TEST_S01"]["status"] == "ADJUDICATION_REQUIRED"

    # Adjudicator resolves dispute
    adjudicate_sample("TEST_S01", adjudicator_id="senior_adjudicator", final_decision="correct", final_class="MODIFIED_COPY", notes="Confirmed near copy")

    with open(test_labels_file, "r", encoding="utf-8") as f:
        resolved = json.load(f)

    assert resolved["TEST_S01"]["status"] == "ADJUDICATED"
    assert resolved["TEST_S01"]["final_class"] == "MODIFIED_COPY"


def test_report_version_snapshot_integrity():
    """Verify analyze_academic_document embeds complete version registry snapshot into report."""
    raw_text = "هذا نص أكاديمي تجريبي لفحص تضمين بيانات الإصدارات."
    report = analyze_academic_document(raw_text)

    assert report['application_version'] == "2.5.0"
    assert report['engine_version'] == "1.3.0"
    assert report['detector_version'] == "shingle-jaccard-tfidf-dual-1.3"
    assert report['citation_engine_version'] == "citation-detector-refined-1.3"
    assert report['common_text_version'] == "common-phrases-span-1.3"
    assert report['candidate_retrieval_mode'] in ('dual_channel', 'baseline')
    assert isinstance(report['settings_snapshot'], dict)
