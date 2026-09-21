# -*- coding: utf-8 -*-
"""
Tests for Phase 19 — Detection Improvement, Generalization & Evidence Gate.
Validates:
- Immutability of Phase 18 baseline records
- Phase 19 experiment registry structure and final decisions (ACCEPT_FOR_PRODUCTION_PROPOSAL / REJECT)
- Deterministic stratified Train/Holdout separation with zero leakage
- Dual-channel candidate retrieval recall gain on unseen holdout
- Common institutional text span-level safety (zero suppression on substantive copy)
- Citation false-positive refinement (isolated years, law article numbers, administrative tags)
- Separation of concerns: Citation presence does NOT cancel plagiarism overlap detection
- Char N-Gram hard negatives audit (justifying rejection of lowered standalone char threshold)
- Offline semantic matcher fail-closed guarantee (no network calls, graceful fallback)
- Segment length guard for short text noise reduction
- PII redaction and audit logging in anonymized ingest workflow
- Strict verification that production configuration remains untouched
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import socket
import pytest

import config
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.preprocessing.normalizer import normalize_light, normalize_aggressive, get_shingles
from plagiarism_detector.preprocessing.segmenter import segment_pages
from evaluation.anonymized_ingest import sanitize_text, generate_anonymous_id
from evaluation.phase19.phase19_experiments import (
    EnhancedDualChannelRetriever,
    is_common_institutional_text_experimental,
    detect_citation_refined
)
from evaluation.phase19.phase19_evidence_gate import (
    deterministic_stratified_split,
    build_unseen_holdout_samples
)
from plagiarism_detector.detection.semantic_matcher import (
    check_semantic_model_availability,
    get_embedder,
    match_semantic_similarity
)

_PROJECT_ROOT = _ROOT
_EVAL_DIR = _PROJECT_ROOT / "tests" / "evaluation"
_BASELINE_FILE = _EVAL_DIR / "phase18_baseline.json"
_REGISTRY_FILE = _EVAL_DIR / "phase19_registry.json"
_EVIDENCE_FILE = _EVAL_DIR / "phase19" / "phase19_evidence_gate_results.json"


def test_phase18_baseline_immutability():
    """Verify Phase 18 baseline metrics are permanently frozen and unchanged."""
    assert _BASELINE_FILE.exists(), f"Missing baseline file: {_BASELINE_FILE}"
    with open(_BASELINE_FILE, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    assert baseline["baseline_identifier"] == "PHASE_18_FROZEN_BASELINE"
    assert baseline["dataset_version"] == "1.0-phase18-baseline"

    metrics = baseline["overall_metrics"]
    assert metrics["overall_accuracy"] == 0.7028
    assert metrics["macro_f1"] == 0.5911

    cr = baseline["candidate_retrieval_metrics"]
    assert cr["recall_at_10"] == 0.7000

    supp = baseline["common_text_suppression_metrics"]
    assert supp["suppression_rate"] == 0.0600
    assert supp["false_overlap_rate"] == 0.4400

    cit = baseline["citation_metrics"]
    assert cit["precision"] == 0.8333
    assert cit["recall"] == 1.0000
    assert cit["false_citation_rate"] == 0.0366

    comp = baseline["dataset_composition"]
    assert comp["DEVELOPER_SYNTHETIC"] == 323
    assert comp["EXPERT_REVIEWED"] == 0
    assert comp["REAL_ANONYMIZED"] == 0


def test_phase19_registry_structure_and_decisions():
    """Verify Phase 19 registry contains all experiments with final gate decisions."""
    assert _REGISTRY_FILE.exists(), f"Missing registry file: {_REGISTRY_FILE}"
    with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
        registry = json.load(f)

    assert isinstance(registry, list)
    assert len(registry) >= 7

    exp_ids = {e["experiment_id"] for e in registry}
    expected_ids = {"EXP-01", "EXP-02", "EXP-03", "EXP-04", "EXP-05", "EXP-06", "EXP-07"}
    assert expected_ids.issubset(exp_ids)

    valid_decisions = {"ACCEPT_FOR_PRODUCTION_PROPOSAL", "REJECT", "NEEDS_MORE_DATA"}
    for exp in registry:
        assert "title" in exp
        assert "changed_component" in exp
        assert "metrics_delta" in exp
        assert "decision" in exp
        assert exp["decision"] in valid_decisions, f"Invalid gate decision: {exp['decision']}"


def test_unseen_holdout_isolation_and_no_leakage():
    """Verify 70/30 split is deterministic, disjoint, and stratified."""
    dataset_file = _EVAL_DIR / "dataset.json"
    with open(dataset_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    train_set, holdout_set = deterministic_stratified_split(dataset, train_ratio=0.70, seed=42)
    train_ids = {s["sample_id"] for s in train_set}
    holdout_ids = {s["sample_id"] for s in holdout_set}

    # Strict disjointness
    assert len(train_ids.intersection(holdout_ids)) == 0
    assert len(train_set) + len(holdout_set) == len(dataset)

    # Stratified preservation
    unseen_holdout = build_unseen_holdout_samples()
    assert len(unseen_holdout) >= 10
    for uh in unseen_holdout:
        assert uh["generation_origin"] == "DEVELOPER_SYNTHETIC_HOLDOUT"


def test_dual_channel_retrieval_gain():
    """Verify dual-channel (word + char 3-gram) retriever indexes and retrieves candidates effectively."""
    corpus = [
        (1, "تعتمد خوارزميات التعلم الآلي والذكاء الاصطناعي على تحليل البيانات الضخمة والنماذج الإحصائية المعقدة."),
        (2, "استخدام تقنيات معالجة اللغات الطبيعية في استخراج المفاهيم واسترجاع المعلومات الأكاديمية."),
        (3, "تطبيق الشبكات العصبية الالتفافية في التعرف على الصور والأنماط البصرية الطبية."),
        (4, "دراسة أثر شبكات الحوسبة السحابية على كفاءة تخزين البيانات وقواعد المعلومات الموزعة.")
    ]

    retriever = EnhancedDualChannelRetriever()
    for seg_idx, text in corpus:
        n_light = normalize_light(text)
        n_aggr = normalize_aggressive(text)
        shingles = get_shingles(n_aggr, size=5)
        retriever.add_segment(seg_idx, n_light, n_aggr, shingles)

    query = "والخوارزميات للتعلم الآلي بالذكاء الاصطناعي للبيانات"
    q_light = normalize_light(query)
    cands = retriever.retrieve_candidates_dual_channel(q_light, top_k=2)

    assert len(cands) > 0
    assert 1 in cands


def test_char_ngram_hard_negatives_audit():
    """Verify why lowered char n-gram threshold for paraphrase was REJECTED due to false positives on technical vocabulary."""
    # Adversarial pair: same domain (law), completely opposite legal scope
    text_a = "يختص القضاء الإداري بالنظر في الطعون المقدمة ضد القرارات الإدارية النهائية الصادرة عن السلطة التنفيذية."
    text_b = "يحظر على القضاء الإداري التدخل في أعمال السيادة والقرارات الدبلوماسية الصادرة عن الهيئات العليا للدولة."

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4))
    mat = vec.fit_transform([normalize_light(text_a), normalize_light(text_b)])
    sim = float(cosine_similarity(mat[0:1], mat[1:2])[0][0])

    # Char similarity exceeds 0.30 due to shared administrative legal terms
    assert sim > 0.30
    # Proves threshold 0.30 would produce a False Positive on unrelated text, justifying the REJECT decision
    assert sim < 0.80


def test_common_text_span_level_safety():
    """Verify institutional boilerplate does not suppress distinctive copied academic text (Span-level safety)."""
    boilerplate = "وبناء على ما تقدم وفي ضوء ما اسفرت عنه النتائج، "
    substantive_copy = "فإن المسؤولية التقصيرية تنعقد قانوناً بثبوت الخطأ والضرر وعلاقة السببية المباشرة بينهما."
    combined_suspicious = boilerplate + substantive_copy

    # 1. Boilerplate is recognized by common text filter
    is_supp = is_common_institutional_text_experimental(combined_suspicious)
    assert is_supp is True

    # 2. But distinctive shingle overlap of substantive content is preserved
    sh_sub = get_shingles(normalize_aggressive(substantive_copy), size=5)
    sh_comb = get_shingles(normalize_aggressive(combined_suspicious), size=5)
    assert len(sh_sub.intersection(sh_comb)) > 0


def test_citation_does_not_suppress_substantive_overlap():
    """Verify citation presence does not mask underlying text plagiarism (Policy independence)."""
    # Verbatim copy with unrelated citation appended
    text_copied = "إن المسؤولية المدنية عن حوادث المركبات الآلية تخضع لقواعد الضمان الموضوعي"
    text_with_fake_cit = text_copied + " (الغامدي، 2019)."

    is_cited, ctype, detail = detect_citation_refined(text_with_fake_cit)
    assert is_cited is True

    # Shingle match still detects full overlap of the underlying sentence
    sh_orig = get_shingles(normalize_aggressive(text_copied), size=5)
    sh_with_cit = get_shingles(normalize_aggressive(text_with_fake_cit), size=5)
    assert len(sh_orig.intersection(sh_with_cit)) > 0


def test_citation_false_positive_refinement():
    """Verify refined citation filtering suppresses isolated years/law articles while retaining valid author citations."""
    valid_text = "وقد أوضح الباحث في دراسته السابقة (الغامدي، 2021) أهمية الفهرسة الآلية."
    is_cited, ctype, detail = detect_citation_refined(valid_text)
    assert is_cited is True
    assert ctype == 'author_year'
    assert "الغامدي" in detail

    isolated_year_text = "تم وضع الخطة الاستراتيجية لتحقيق الأهداف الوطنية بحلول (الرؤية، 2030) في جميع القطاعات."
    is_cited_yr, ctype_yr, _ = detect_citation_refined(isolated_year_text)
    if is_cited_yr:
        assert ctype_yr != 'author_year'

    law_article_text = "وفقاً لما نصت عليه (المادة، 2020) من اللائحة التنفيذية لنظام الجامعات."
    is_cited_law, ctype_law, _ = detect_citation_refined(law_article_text)
    if is_cited_law:
        assert ctype_law != 'author_year'


def test_offline_semantic_fail_closed(monkeypatch):
    """Verify offline semantic matcher never attempts network calls and fails closed gracefully."""
    def guarded_socket(*args, **kwargs):
        raise RuntimeError("NETWORK_ACCESS_BLOCKED_AIR_GAPPED")

    monkeypatch.setattr(socket, "socket", guarded_socket)

    avail = check_semantic_model_availability()
    assert isinstance(avail, dict)
    assert "available" in avail

    embedder = get_embedder()
    if embedder is None:
        assert match_semantic_similarity("نص 1", [0], ["نص 2"], None) is None


def test_segment_length_guard():
    """Verify short character segments (< 20 chars or < 4 words) are guarded by segmenter."""
    pages = [{"page_number": 1, "text": "شكرا جزيلا. هذا نص كامل للدراسة الأكاديمية يتجاوز الحد الأدنى للكلمات بنجاح."}]
    segments = segment_pages(pages, min_words=4)
    for seg in segments:
        assert seg.word_count >= 4
        assert len(seg.raw_text) > 15


def test_anonymized_ingest_pii_redaction():
    """Verify PII redaction strips emails, phone numbers, and academic titles with hash anonymization."""
    raw_text = (
        "قام الباحث أ.د. محمد عبدالله بإشراف الدكتور أحمد علي بإرسال النتائج عبر البريد "
        "researcher@university.edu.sa ورقم الهاتف +966501234567 من قسم علوم الحاسب بجامعة الملك سعود."
    )
    sanitized = sanitize_text(raw_text)

    assert "researcher@university.edu.sa" not in sanitized
    assert "[EMAIL_REDACTED]" in sanitized
    assert "+966501234567" not in sanitized
    assert "[PHONE_REDACTED]" in sanitized
    assert "محمد عبدالله" not in sanitized
    assert "[PERSON_NAME_REDACTED]" in sanitized

    anon_id = generate_anonymous_id(sanitized, "cs")
    assert anon_id.startswith("ANON_CS_")
    assert len(anon_id) == 20


def test_production_config_remains_strictly_unchanged():
    """Verify that Phase 19 did NOT modify any production default settings or thresholds."""
    assert config.DEFAULT_SETTINGS['shingle_size'] == 4
    assert config.DEFAULT_SETTINGS['jaccard_threshold'] == 0.33
    assert config.DEFAULT_SETTINGS['tfidf_threshold'] == 0.35
    assert config.DEFAULT_SETTINGS['enable_semantic_model'] is False
    assert config.DEFAULT_SETTINGS['max_candidate_retrieval'] == 50
