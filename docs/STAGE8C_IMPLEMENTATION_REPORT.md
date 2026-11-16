# Stage 8C — research baseline implementation

## Status and integration

**Research infrastructure implemented; no production AI-writing model is validated or enabled.** Existing upload/scan services extract page data and send it to the plagiarism report builder. The report already carries `ai_analysis`; its unavailable/error state is independent of similarity calculations. No app inference path, database migration, model deployment, or AI percentage was added. The flag remains disabled by default and enabling it still yields `no_validated_model`. The existing integration tests check unchanged similarity output and failure isolation; multi-file extraction is checked using a mock. Neither a real classifier nor a browser-to-model workflow exists to test.

## Data availability and license review

The only locally identified Stage 8 dataset is `tests/benchmark/stage8_ai_writing_synthetic.json`: two developer-synthetic records, intended only for tests. It has no valid independent train/validation/test evaluation and cannot establish accuracy. Existing Stage 8B tools check declared provenance, permission, Arabic content, group leakage, normalized exact duplicates and near-duplicate candidates; these checks are not a substitute for a curator or legal review.

* [KFUPM Arabic-generated abstracts](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts) and its [project](https://github.com/KFUPM-JRCAI/arabic-text-detection) describe academic abstracts and multiple generators, including polishing. The code repository is MIT-licensed; dataset-specific rights, upstream journal-text rights, retention and derivative-model permissions have not been established. Original-label quality, linked source IDs, duplicates and split leakage have not been independently checked. Not acquired.
* [ALHD v2](https://zenodo.org/records/22829905) is now discoverable on Zenodo, superseding the earlier Stage 8B discovery gap. It describes news, social media and reviews rather than academic Arabic. The version offers files totaling 4 GB; data-specific reuse rights, provenance and group leakage were not independently confirmed here. Not acquired. It could be an out-of-domain challenge set after rights and data-quality review, not an academic deployment-validation substitute.
* [MULTITuDE](https://zenodo.org/records/10013755) is documented in Stage 8B as a CC BY external-evaluation candidate; its Arabic subset is news-domain and the archived license and upstream rights must still be checked. Not acquired.
* Stage 8B documents GRACE shared-task restrictions and unresolved Ar-APT permissions. No permission to acquire these for this project is established.

No private or public source was downloaded, no corpus class counts or near-duplicate rates were measured, and there is no independent Arabic academic test set. A real training run requires licensed, provenance-labeled material with traceable document, author, source, prompt and generator groups as available, curated deduplication and independently reviewed train/validation/test splits, plus representative human, AI, mixed and AI-polished evaluation material. Curator attestations in a manifest are not proof of data quality or legal rights.

## Implemented research-only tooling

`plagiarism_detector/ai_detection/baseline.py` adds sparse word and character TF-IDF (float32; bounded vocabulary) with balanced logistic regression or linear SVM. Original text is passed directly to TF-IDF; no destructive Arabic normalization is applied. Vectorizers and classifier fit training data only. A separate logistic calibrator fits validation scores; the candidate threshold searches for the highest observed validation recall at an observed FPR strictly below 2%. Tiny validation sets, selection on the calibration set, and model/feature tuning produce optimistic and unstable estimates: use independent calibration/threshold data or nested validation and confidence bounds before deployment. No population FPR guarantee follows from this threshold.

The input gate requires an acquired manifest, affirmative research-use and curation attestations (except for explicitly marked fixtures), valid binary labels, permissions, Arabic text, all three splits with both classes, group separation and no detected cross-split exact or near duplicates. It does not prove all data is licensed, independently labeled or academically representative, and the current pairwise near-duplicate candidate generation can be expensive for a large corpus. Edited and mixed cases are not silently assigned binary labels; the current baseline accepts only HUMAN and AI_GENERATED. It does not yet provide subgroup, mixed-content or percentage-error evaluation, or an uncertainty class. FPR and FNR have approximate 95% Wilson intervals; these assume independent observations and can be overconfident for correlated passages.

The CLI makes training and evaluation separate. It never reads model artifacts in the application and never downloads files. It records the raw dataset SHA-256 and fixture status in the serialized pipeline and requires the same dataset for evaluation. `joblib`/pickle loading executes code: load only artifacts created locally from trusted inputs. Do not distribute these research artifacts or enable them as production models.

```powershell
python -m tools.stage8c_baseline train --dataset DATA.json --manifest MANIFEST.json --artifact MODEL.joblib --kind logistic --features both
python -m tools.stage8c_baseline evaluate --dataset DATA.json --manifest MANIFEST.json --artifact MODEL.joblib --split validation --threshold 0.5
# Fix model/configuration/threshold before a separate final test evaluation.
python -m tools.stage8c_baseline evaluate --dataset DATA.json --manifest MANIFEST.json --artifact MODEL.joblib --split test --threshold CHOSEN_THRESHOLD
```

`--fixture` is required for developer-synthetic input and brands the output as fixture-only. The CLI does not technically enforce one-time test access or freeze selection; research procedure must do so. Training refuses to overwrite an existing artifact. Calibration Brier score and binary metrics are calculated, but no model is claimed calibrated in the scientific sense without independent assessment.

## Model comparison and measurements

| Candidate | Accuracy | Precision | Recall | F1 | FPR | Speed | Peak RAM | Disk size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TF-IDF + logistic regression | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | No real model |
| TF-IDF + linear SVM | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | No real model |
| Farras | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not local |
| Fine-tuned AraBERT | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not local |
| Quantized Arabic classifier | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not local |

The Farras [repository](https://github.com/Rashidbm/farras) describes limitations, while the [model page](https://huggingface.co/Rashidbm/farras-xlmr-arabic-ai-detector) lacks a model card; weights, license, domain validity and hardware must be independently verified. General AraBERT is not an authorship detector. Local E5 is a retrieval embedder. No eligible classifier, representative documents, or target i3/4 GB machine was available; no accuracy, CPU, memory, cold/warm, 1,000-word or 10/50/100-page inference measurements were made. No ONNX conversion or quantization is justified yet. Research fixture training demonstrates software operation only, not detection performance.

The development machine is Windows 11 Home, i5-12500H, 12 cores/16 logical processors, approximately 31.7 GiB RAM, Python 3.13.2. Its results cannot establish compatibility with the 4 GB total-system target. Existing environment versions are NumPy 2.5.2, SciPy 1.15.2, scikit-learn 1.6.1; SciPy reports NumPy must be >=1.23.5 and <2.5.0. No dependency versions were changed; use a separately managed compatible environment and revalidate before scientific benchmarking or release.

## Tests and release work

Targeted command: `python -m pytest -q --disable-warnings tests/test_stage8c_baseline.py tests/test_ai_analysis_integration.py tests/test_stage8b_dataset_validation.py`: **26 passed**, 197 warnings, 12.25 seconds. This includes both model types and feature configurations, calibration/metrics, fixture-only local loading, network blocking in fixture inference, separate test data, cross-split leakage, missing permission, CLI execution and overwrite protection. Fixture metrics are intentionally not reported as model accuracy.

The full `python -m pytest -q --disable-warnings` run started before the new Stage 8C test file was created: **862 passed, 3 failed, 3,285 warnings in 276.37 seconds**. It is not a full passing current-state regression. One failure is `tests/test_release_candidate.py::test_release_manifest_integrity_and_hashes`: the previously modified `config.py` does not match the checked-in release manifest; no manifest was rewritten or release rebuilt. Two failures are `tests/test_review_history_similarity.py::test_preliminary_history_contributes_to_official_similarity` and `::test_rejected_history_is_separate_from_official_similarity`, each expecting 100% and receiving 0%. Both reproduced in a focused rerun, which also ran the new tests: **28 passed, 2 failed**, 208 warnings in 14.22 seconds. Source inspection suggests the Stage 2 aligned-token count is created for corpus matches before review-history matching, while the later review-history paths do not independently populate it; this needs a dedicated scoring repair and validation. The present work intentionally does not alter similarity scoring. No skips were reported in either summary.

There is no selected model to package. A future package requires a separately approved model, local-only tokenizer/vectorizer and runtime, pinned compatible dependencies, hash-verified artifacts, saved preprocessing and calibration/threshold metadata, trusted serialization or a safe model format, error handling, and tests of the actual Windows executable without network access. On a standalone PC benchmark the full application under the 4 GB system budget; for a central LAN server bound concurrency and test aggregate memory/load. The future steps are authorized data acquisition and review, leakage-resistant held-out evaluation including edited/mixed documents, baseline comparison, model and threshold selection without test-set tuning, target-machine optimization benchmarking, then opt-in production integration and end-to-end validation.
