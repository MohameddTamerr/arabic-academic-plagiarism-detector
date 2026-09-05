# Immutable Baseline Snapshot: Release v1.0.0-rc1

This document freezes the baseline state, configuration, evaluation metrics, and cryptographic file hashes of **Release v1.0.0-rc1** prior to the implementation of `v1.0.0-rc2` pilot enhancements.

---

## 1. Release Identity & Versions

- **Release Version:** `v1.0.0-rc1`
- **Application Version:** `2.4.0`
- **Engine Version:** `1.2.0`
- **Database Schema Version:** `1.0.0`
- **Report Schema Version:** `1.0`
- **Normalization Version:** `arabic-normalizer-1.0`
- **Detector Version:** `shingle-jaccard-tfidf-1.0`
- **Citation Engine Version:** `citation-detector-1.0`
- **Common Text Handling Version:** `common-phrases-1.0`
- **Test Baseline:** 559 tests passing (0 failures, 0 regressions)

---

## 2. Production Detector Configuration

```python
DEFAULT_SETTINGS = {
    'shingle_size': 5,                     # Word shingles n-gram (k=5)
    'jaccard_threshold': 0.40,             # Direct copy threshold (>= 40%)
    'tfidf_threshold': 0.40,               # Lexical paraphrase threshold (>= 40%)
    'semantic_threshold': 0.70,            # Semantic threshold (>= 70%)
    'min_sentence_words': 4,               # Minimum sentence length
    'allowed_similarity_pct': 20.0,        # Institutional overall threshold
    'words_per_page': 250,                 # Page word estimation
    'max_allowed_pages_per_source': 5.0,   # Max source allowance
    'enable_semantic_model': False,        # Disabled offline
    'enable_ocr': True,                    # Conditional OCR
    'detection_profile': 'LIGHT',          # Profile: LIGHT (Jaccard + TF-IDF)
    'max_candidate_retrieval': 50,         # Top-k candidate retrieval
}
```

---

## 3. Measured Detection Metrics (Phase 18 Baseline)

- **Dataset Provenance:** 323 DEVELOPER_SYNTHETIC, 0 EXPERT_REVIEWED, 0 REAL_ANONYMIZED
- **Exact Copy (`EXACT_COPY`):** Precision 100.0%, Recall 98.18%, F1 0.9908
- **Modified Copy (`MODIFIED_COPY`):** Precision 97.37%, Recall 67.27%, F1 0.7957
- **Paraphrase (`PARAPHRASE`):** Precision 0.00%, Recall 0.00%, F1 0.0000
- **Citation Detection:** Precision 83.33%, Recall 100.00%, F1 0.9091 (False citation rate: 3.66%)
- **Common Text Suppression:** Suppression rate 6.00%, False overlap rate 44.00%
- **Candidate Retrieval Recall@10:** 52.78% (evaluation sweep), ~70% (token union)

---

## 4. Phase 19 Proposals Status in RC1

- **EXP-01 (Dual-Channel Retrieval):** `ACCEPT_FOR_PRODUCTION_PROPOSAL`, NOT DEPLOYED in RC1.
- **EXP-02 (Standalone Char TF-IDF Paraphrase):** `REJECTED`, NOT DEPLOYED.
- **EXP-03 (Span-Level Common-Text Filter):** `ACCEPT_FOR_PRODUCTION_PROPOSAL`, NOT DEPLOYED in RC1.
- **EXP-04 (Refined Citation Filter):** `ACCEPT_FOR_PRODUCTION_PROPOSAL`, NOT DEPLOYED in RC1.
- **EXP-05 (Semantic Fail-Closed):** `CONFIRMED_BASELINE`, DEPLOYED in RC1.
- **EXP-06 (Segment Length Guard):** `CONFIRMED_BASELINE`, DEPLOYED in RC1.
- **EXP-07 (Shingle k=5 Confirmation):** `CONFIRMED_BASELINE`, DEPLOYED in RC1.
