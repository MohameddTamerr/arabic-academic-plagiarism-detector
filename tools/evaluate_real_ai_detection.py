"""Comprehensive evaluation of Arabic AI Writing Detectors and Baselines on Academic Benchmark."""
import os, sys, json, math, time, hashlib
from pathlib import Path
from collections import Counter
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, brier_score_loss
)

from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter, file_sha256

def wilson_ci(k, n, confidence=0.95):
    if n == 0:
        return [0.0, 0.0]
    z = 1.959963984540054 if confidence == 0.95 else 1.6448536269514722
    p = k / n
    denom = 1 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + (z ** 2) / (4 * n)) / n) / denom
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]

def compute_metrics(y_true, y_pred, y_probs=None):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    auc = None
    brier = None
    if y_probs is not None:
        try:
            auc = roc_auc_score(y_true, y_probs)
        except Exception:
            auc = None
        try:
            brier = brier_score_loss(y_true, y_probs)
        except Exception:
            brier = None

    return {
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "accuracy": round(float(acc), 4),
        "precision": round(float(prec), 4),
        "precision_95_ci": wilson_ci(int(tp), int(tp + fp)),
        "recall_sensitivity": round(float(rec), 4),
        "recall_95_ci": wilson_ci(int(tp), int(tp + fn)),
        "specificity": round(float(spec), 4),
        "specificity_95_ci": wilson_ci(int(tn), int(tn + fp)),
        "false_positive_rate": round(float(fpr), 4),
        "fpr_95_ci": wilson_ci(int(fp), int(fp + tn)),
        "false_negative_rate": round(float(fnr), 4),
        "fnr_95_ci": wilson_ci(int(fn), int(fn + tp)),
        "f1_score": round(float(f1), 4),
        "roc_auc": round(float(auc), 4) if auc is not None else None,
        "brier_score": round(float(brier), 4) if brier is not None else None
    }

def fit_tfidf_baseline(train_records, val_records, kind='svm'):
    vectors = [
        ('word', TfidfVectorizer(token_pattern=r'(?u)\b\w+\b', ngram_range=(1, 2), max_features=15000, dtype=np.float32)),
        ('char', TfidfVectorizer(analyzer='char', ngram_range=(3, 5), max_features=15000, dtype=np.float32))
    ]
    clf = LinearSVC(class_weight='balanced', random_state=8) if kind == 'svm' else LogisticRegression(max_iter=1000, class_weight='balanced', random_state=8)
    pipeline = Pipeline([('features', FeatureUnion(vectors)), ('classifier', clf)])
    X_train = [r['text'] for r in train_records]
    y_train = [1 if r['provenance_label'] == 'AI_GENERATED' else 0 for r in train_records]
    pipeline.fit(X_train, y_train)

    # Calibrate probability mapping on validation set
    X_val = [r['text'] for r in val_records]
    y_val = [1 if r['provenance_label'] == 'AI_GENERATED' else 0 for r in val_records]
    scores_val = pipeline.decision_function(X_val).reshape(-1, 1)
    calibrator = LogisticRegression(random_state=8).fit(scores_val, y_val)

    def predict_probs(texts):
        scores = pipeline.decision_function(texts).reshape(-1, 1)
        return calibrator.predict_proba(scores)[:, 1]

    return pipeline, predict_probs

def main():
    dataset_file = _ROOT / "tests" / "benchmark" / "academic_ai_writing_benchmark_dataset.json"
    records = json.loads(dataset_file.read_text(encoding="utf-8"))

    train_recs = [r for r in records if r['split'] == 'train']
    val_recs = [r for r in records if r['split'] == 'validation']
    test_recs = [r for r in records if r['split'] == 'test']
    test_binary = [r for r in test_recs if r['provenance_label'] in ('HUMAN', 'AI_GENERATED')]
    test_edited = [r for r in test_recs if r['provenance_label'] == 'AI_EDITED']

    print(f"Loaded: train={len(train_recs)}, val={len(val_recs)}, test_binary={len(test_binary)}, test_edited={len(test_edited)}")

    # 1. Train Baselines
    print("\n--- Fitting TF-IDF + SVM Baseline ---")
    svm_pipe, svm_predict_probs = fit_tfidf_baseline(train_recs, val_recs, kind='svm')
    print("--- Fitting TF-IDF + Logistic Regression Baseline ---")
    log_pipe, log_predict_probs = fit_tfidf_baseline(train_recs, val_recs, kind='logistic')

    # 2. Neural Model Adapters
    h_nawaf = json.loads((_ROOT / "scratch" / "stage8f" / "hashes_nawaf.json").read_text("utf-8"))
    h_sabari = json.loads((_ROOT / "scratch" / "stage8f" / "hashes.json").read_text("utf-8"))

    print("\n--- Initializing Nawaf FP32 Adapter ---")
    ad_nawaf_fp32 = SequenceResearchAdapter(
        str(_ROOT / "scratch" / "stage8f" / "nawaf"),
        file_hashes=h_nawaf, label_mapping={0: 'HUMAN', 1: 'AI_GENERATED'}, mapping_evidence='nawaf card', batch_size=4
    )

    print("--- Initializing Nawaf INT8 TorchScript Adapter ---")
    m_nawaf_jit = _ROOT / "scratch" / "stage8h" / "nawaf_int8.jit"
    m_nawaf_manifest = _ROOT / "scratch" / "stage8h" / "nawaf_int8.manifest.json"
    m_hash = file_sha256(m_nawaf_manifest)
    ad_nawaf_int8 = SequenceResearchAdapter(
        str(_ROOT / "scratch" / "stage8f" / "nawaf"),
        file_hashes=h_nawaf, label_mapping={0: 'HUMAN', 1: 'AI_GENERATED'}, mapping_evidence='nawaf card',
        scripted_artifact=str(m_nawaf_jit), scripted_mode='int8', scripted_manifest_sha256=m_hash, batch_size=4
    )

    print("--- Initializing Sabaridsnfuji FP32 Adapter ---")
    ad_sabari_fp32 = SequenceResearchAdapter(
        str(_ROOT / "scratch" / "stage8f" / "sabaridsnfuji"),
        file_hashes=h_sabari, label_mapping={0: 'HUMAN', 1: 'AI_GENERATED'}, mapping_evidence='sabari card', batch_size=4
    )

    models = {
        "TF-IDF + LinearSVC": lambda texts: svm_predict_probs(texts),
        "TF-IDF + LogisticRegression": lambda texts: log_predict_probs(texts),
        "Nawaf AraBERT (FP32)": lambda texts: [ad_nawaf_fp32.analyze([{'text': t, 'paragraph_id': i}])[0]['scores']['AI_GENERATED'] for i, t in enumerate(texts)],
        "Nawaf AraBERT (INT8 JIT)": lambda texts: [ad_nawaf_int8.analyze([{'text': t, 'paragraph_id': i}])[0]['scores']['AI_GENERATED'] for i, t in enumerate(texts)],
        "Sabaridsnfuji AraBERT (FP32)": lambda texts: [ad_sabari_fp32.analyze([{'text': t, 'paragraph_id': i}])[0]['scores']['AI_GENERATED'] for i, t in enumerate(texts)],
    }

    full_report = {
        "benchmark_dataset_summary": {
            "dataset_file": str(dataset_file),
            "splits": {
                "train": len(train_recs),
                "validation": len(val_recs),
                "test_binary": len(test_binary),
                "test_edited": len(test_edited)
            }
        },
        "models_evaluated": {}
    }

    y_val = np.array([1 if r['provenance_label'] == 'AI_GENERATED' else 0 for r in val_recs])
    y_test = np.array([1 if r['provenance_label'] == 'AI_GENERATED' else 0 for r in test_binary])
    X_val = [r['text'] for r in val_recs]
    X_test = [r['text'] for r in test_binary]

    print("\n" + "="*80)
    print("                 BENCHMARK EVALUATION RESULTS")
    print("="*80)

    for name, predictor in models.items():
        print(f"\n>>> Evaluating: {name}...")
        t0 = time.perf_counter()
        probs_val = np.array(predictor(X_val))
        val_time = time.perf_counter() - t0

        t1 = time.perf_counter()
        probs_test = np.array(predictor(X_test))
        test_time = time.perf_counter() - t1

        # Standard decision threshold = 0.50
        preds_test = (probs_test >= 0.50).astype(int)
        test_metrics = compute_metrics(y_test, preds_test, probs_test)

        # Calibrated decision threshold on validation set (best F1 on val)
        best_tau = 0.50
        best_val_f1 = -1
        for tau in np.linspace(0.1, 0.9, 81):
            f1_cand = f1_score(y_val, (probs_val >= tau).astype(int), zero_division=0)
            if f1_cand > best_val_f1:
                best_val_f1 = f1_cand
                best_tau = round(float(tau), 4)

        preds_calibrated = (probs_test >= best_tau).astype(int)
        calibrated_test_metrics = compute_metrics(y_test, preds_calibrated, probs_test)

        # Abstention evaluation: abstaining in uncertain region [0.5 - 0.15, 0.5 + 0.15] = [0.35, 0.65]
        abstain_low, abstain_high = 0.35, 0.65
        abstained_mask = (probs_test > abstain_low) & (probs_test < abstain_high)
        classified_mask = ~abstained_mask
        n_classified = int(np.sum(classified_mask))
        if n_classified > 0:
            abstain_acc = accuracy_score(y_test[classified_mask], (probs_test[classified_mask] >= 0.50).astype(int))
            human_classified = (y_test[classified_mask] == 0)
            fpr_abstain = float(np.mean((probs_test[classified_mask][human_classified] >= 0.50))) if np.sum(human_classified) > 0 else 0.0
        else:
            abstain_acc, fpr_abstain = None, None

        # Domain breakdown on test set
        domain_results = {}
        for dom in ['law_and_criminology', 'security_and_policing', 'diplomacy_and_protocol', 'computer_and_education', 'humanities_and_rights']:
            dom_idx = [i for i, r in enumerate(test_binary) if r['academic_domain'] == dom]
            if dom_idx:
                dom_y = y_test[dom_idx]
                dom_preds = preds_test[dom_idx]
                domain_results[dom] = {
                    "count": len(dom_idx),
                    "human_count": int(np.sum(dom_y == 0)),
                    "ai_count": int(np.sum(dom_y == 1)),
                    "accuracy": round(float(accuracy_score(dom_y, dom_preds)), 4),
                    "fp_count": int(np.sum((dom_y == 0) & (dom_preds == 1))),
                    "fn_count": int(np.sum((dom_y == 1) & (dom_preds == 0))),
                }

        # Generator breakdown on test AI samples
        gen_results = {}
        ai_indices = [i for i, r in enumerate(test_binary) if r['provenance_label'] == 'AI_GENERATED']
        for i in ai_indices:
            gen = test_binary[i]['generator_family']
            score = probs_test[i]
            gen_results.setdefault(gen, []).append(round(float(score), 4))
        generator_summary = {g: {"count": len(sc), "mean_score": round(float(np.mean(sc)), 4), "detected_ai_rate": round(float(np.mean(np.array(sc) >= 0.50)), 4)} for g, sc in gen_results.items()}

        # AI-Edited / Polished evaluation
        edited_texts = [r['text'] for r in test_edited]
        probs_edited = predictor(edited_texts)
        edited_summary = []
        for r, score in zip(test_edited, probs_edited):
            edited_summary.append({
                "source": r['source_document_id'],
                "domain": r['academic_domain'],
                "generator": r['generator_family'],
                "ai_score": round(float(score), 4),
                "verdict_tau_50": "AI_GENERATED" if score >= 0.50 else "HUMAN"
            })

        model_entry = {
            "validation_time_sec": round(val_time, 3),
            "test_time_sec": round(test_time, 3),
            "ms_per_paragraph": round(test_time / len(X_test) * 1000, 2),
            "default_threshold_0_50": test_metrics,
            "calibrated_threshold": {
                "selected_tau": best_tau,
                "metrics": calibrated_test_metrics
            },
            "abstention_analysis_range_0_35_to_0_65": {
                "total_samples": len(test_binary),
                "abstained_count": int(np.sum(abstained_mask)),
                "classified_coverage": round(n_classified / len(test_binary), 4),
                "accuracy_among_classified": round(float(abstain_acc), 4) if abstain_acc is not None else None,
                "fpr_among_classified_human": round(float(fpr_abstain), 4) if fpr_abstain is not None else None
            },
            "subgroup_by_domain": domain_results,
            "subgroup_by_ai_generator": generator_summary,
            "ai_polished_human_writing_evaluation": {
                "count": len(test_edited),
                "mean_ai_score": round(float(np.mean(probs_edited)), 4),
                "classified_as_ai_ratio": round(float(np.mean(np.array(probs_edited) >= 0.50)), 4),
                "samples": edited_summary
            }
        }
        full_report["models_evaluated"][name] = model_entry

        print(f"  F1: {test_metrics['f1_score']} | Acc: {test_metrics['accuracy']} | Rec: {test_metrics['recall_sensitivity']} | Prec: {test_metrics['precision']}")
        print(f"  FPR (False Accusation Rate on Human Theses): {test_metrics['false_positive_rate'] * 100:.2f}% (95% CI: {test_metrics['fpr_95_ci']})")
        print(f"  ROC-AUC: {test_metrics['roc_auc']}")
        print(f"  AI-Polished Human Classified as AI: {model_entry['ai_polished_human_writing_evaluation']['classified_as_ai_ratio'] * 100:.1f}%")

    out_report = _ROOT / "docs" / "REAL_AI_DETECTION_EVALUATION_REPORT.json"
    out_report.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] Saved comprehensive evaluation report to: {out_report}")

if __name__ == '__main__':
    main()
