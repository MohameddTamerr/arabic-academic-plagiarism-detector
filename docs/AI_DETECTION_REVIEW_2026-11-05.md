# Offline AI detection review — 2026-11-05

## Decision

No model can be selected or benchmarked from the available evidence. The application only returns an unavailable AI status; it has no validated classifier or AI inference runtime. The local Stage 8 fixture contains two developer-synthetic records, not an independent evaluation set. The local E5 ONNX model is a similarity retrieval embedder, not an AI-authorship classifier. No training or model download was performed.

| Model | Accuracy | Precision | Recall | F1 | False positive rate | Processing time | Peak RAM | Model size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TF-IDF + SVM / logistic regression | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | No trained artifact |
| Farras | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not present locally |
| Fine-tuned AraBERT | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not present locally |
| Quantized Arabic classifier | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not present locally |

False-negative rate, calibration, paragraph accuracy and document-percentage error, including separate academic, mixed and AI-polished conditions, are likewise unmeasured. All requested inference timing by word count and 10/50/100-page document, cold/warm loading, CPU utilization, and peak memory are unmeasured. There is no before/after inference optimization benchmark and no performance improvement is claimed. The E5 retrieval model file is 118,308,811 bytes; this is not an AI-detector model size and does not establish detector performance.

## Review and changes

The scan service passes extracted page data once to the shared report builder. The existing research workflow has an exact-file-match shortcut that can reuse stored pages instead. In the ordinary path the AI status does not extract or process the document again. The AI status and plagiarism values are serialized in the same report. This is status integration, not two functioning analyses.

An exception boundary now isolates failures in the AI status provider: the similarity report continues, the AI status is `unavailable` / `analysis_error`, no percentage is fabricated, and the UI and HTML export identify an error. The log does not include exception details or document text. Existing scoring code is unchanged. The existing multi-file pipeline test now checks one mocked extraction call per input file and both report fields. It is a pipeline test with mocked extraction, not an end-to-end browser upload or a real AI-inference test. An injected AI failure test checks similarity results against a baseline.

Actual validation: `python -m pytest -q --disable-warnings tests/test_ai_analysis_integration.py tests/test_batch.py tests/test_extraction.py tests/test_ui_shell.py tests/test_integration_qa.py tests/test_stage8_dataset_readiness.py tests/test_stage8b_dataset_validation.py` — 93 passed, 855 warnings in 4.37 s. Warnings include a NumPy/SciPy version compatibility warning and deprecations. This is not a full-suite or packaged-executable test. No live upload, browser rendering, model inference, or LAN performance test was performed.

## Hardware and deployment

Test host: HP Victus 15-fa0xxx, Intel Core i5-12500H, 12 cores / 16 logical processors, approximately 31.7 GiB RAM, Windows 11 Home build 26300, Python 3.13.2. This is substantially stronger than the target i3/4 GB machine. No conclusion about model runtime or 4 GB compatibility follows from these tests.

The current unavailable path loads no AI model, adds no online service or database migration, and works with the existing local/server architecture. A future offline package must include approved model weights, tokenizer/vectorizer and preprocessing assets, runtime and dependencies, explicit model version and hashes, and calibration and threshold metadata. It must forbid downloads at runtime, validate artifacts, fail closed on missing/corrupt assets, and limit inference workers and CPU threads. Do not load large AI and semantic models simultaneously on low-memory PCs without measurements. For LAN, run the same backend on the central server with bounded per-server concurrency and test memory at the target user load; browser clients do not perform inference.

## Next steps

1. Acquire authorized, independently labeled Arabic academic data, including human, AI, mixed and AI-polished conditions; establish provenance, license, exact and near-duplicate review, and group-disjoint locked test splits. The existing Stage 8B reports describe candidate data and outstanding permissions.
2. Evaluate any existing eligible model first. If none exists, train a sparse linear baseline with approved training data. Choose thresholds using a separate validation set and pre-specified false-positive constraints; compare all models on the same untouched test set and report counts and uncertainty.
3. Measure paragraph results and word-weighted document percentage error, and separately report uncertain and unanalyzed text. Verify calibration and human false positives in each relevant condition.
4. Benchmark cold and warm inference, 1,000 words and representative 10/50/100-page documents, CPU, peak RAM, and model footprint on the actual 4 GB Windows host. Compare batch size, thread limits, lazy loading, sequential operation, and any INT8/ONNX conversion one change at a time, including reliability regressions.
5. Only after passing scientific and hardware gates, implement local-only inference, original-text paragraph segmentation, failure-safe report integration, evidence highlighting and packaging; then verify the actual browser upload and LAN workflows. Keep the feature disabled until independently approved.
