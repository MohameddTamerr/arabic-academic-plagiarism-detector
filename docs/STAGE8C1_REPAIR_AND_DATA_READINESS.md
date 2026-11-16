# Stage 8C.1 — regression repair and data readiness

## Review-history regression

The original focused run reproduced both 100%-versus-0% failures. Review-history matching succeeded, but Stage 2 populated `alignment_evidence` and `matched_token_indexes` only for ordinary corpus matches, before review-history matching. Aggregation therefore counted zero. Rejected-history aggregation additionally reused the ordinary similarity token count, which could either suppress its own evidence or attribute unrelated corpus tokens to a rejected source.

The report builder now aligns a winning preliminary lexical history match to the original submitted text and unions its token indexes with existing lexical evidence. It stores source/report/page metadata for reviewer-evidence compatibility. Rejected lexical matches receive their own separate alignment and token indexes; the rejected signal is calculated from those indexes, not the official count. Semantic-only or non-alignable matches carry explicit coordinate status and do not invent lexical coverage. Source attribution to a history source without aligned evidence is zero, not a fallback to another source's tokens. Existing bibliography suppression, citation treatment, denominator and lexical-union rules remain in place. The legacy repository reads previous report `text` or `suspect_text`; missing/too-short passages cannot be compared and are skipped by the existing reader. Historical report JSON and audit records are not migrated or rewritten. A document-level zero is not proof that skipped historical passages were examined.

New tests cover partially overlapping preliminary and rejected spans, independent percentages, provenance in the reviewer evidence catalogue, and semantic-only non-counting. Both original exact-copy tests pass in the targeted run. This is not a broad reassessment of detector accuracy or legacy-data completeness.

Targeted command: `python -m pytest -q --disable-warnings tests/test_review_history_similarity.py tests/test_span_aligner.py tests/test_span_pdf_highlight.py tests/test_stage6_reviewer_workflow.py tests/test_ai_analysis_integration.py tests/test_stage8c_baseline.py tests/test_release_provenance.py`: **36 passed, 0 failed, 0 skipped**, 374 warnings, 10.04 seconds. The two newly added review-history tests and one data-quality test are also included in the later full run.

Full current-source command: `python -m pytest -q --disable-warnings`: **878 passed, 1 failed, 0 skipped**, 3,386 warnings, 240.92 seconds. The sole failure is the historical source-manifest mismatch described below. Both originally failing review-history tests passed. Warnings include the NumPy/SciPy incompatibility and deprecations; a libpng CRC warning also appeared. The suite was not reported as passing.

## Release manifests

The root `release_manifest.json` is a historical source snapshot and is already modified in the working tree. Its `config.py` hash is `ca3c65...492b`; current source is `22c3e9...e548`. Existing intentional uncommitted settings include retrieval and feature flags. A full hash inventory also found mismatches for report builder, semantic matcher, OCR engine and retrieval index. Some differ even at HEAD, demonstrating that the manifest and current checkout are not the same source snapshot. The strict source-integrity test remains unchanged and correctly fails; neither manifest hashes nor old artifacts were rewritten to make it pass.

Independently, `python -m tools.verify_release_provenance FINAL_RELEASE/windows-modern/Arabic-Plagiarism-System-RC3.exe FINAL_RELEASE/RELEASE_MANIFEST.json FINAL_RELEASE/SHA256SUMS.txt` returned `PASS: artifact, manifest, and SHA256SUMS match exactly`. This validates the recorded RC3 file identity, not equivalence to current development source, its UI, or a new release.

For a new release, review and commit the intended source and assets, create an isolated clean snapshot at that exact revision, run tests in a compatible pinned environment, build and smoke-test there, generate a **new** manifest from the frozen build inputs and resulting artifact, and verify both source hashes and artifact/checksum independently. Preserve historical manifests and packages. Do not replace hashes merely because development changed.

## Dataset audit and research pipeline

The Stage 8C code fits vectorizers/classifier on `train`, score calibration and candidate threshold on `validation`, and computes test metrics only on an explicitly requested evaluation call. Group and cross-split duplicate gates exist. The CLI requires manifest/record permissions and curator attestations, and synthetic mode is explicit. It does not enforce a one-time locked test evaluation; calibration and threshold selection share validation data, so validation metrics may be optimistic. Group checks only cover metadata supplied. Research joblib artifacts are not imported by production, and are unsafe to load from untrusted sources. No model was trained during this stage and the production flag still returns `no_validated_model`.

Added `python -m tools.audit_ai_writing_data DATA.json` (JSONL is supported) to report counts by split and label, invalid and short/empty text, Unicode replacement characters, missing split, non-Arabic content, exact/near duplicates, declared source-group leakage, and topic/generator overlap where metadata exists. Strict UTF-8 decoding raises on invalid byte sequences; replacement-character checking is only a corruption indicator, not a complete encoding validator. Topic/generator overlap is triage, not automatically leakage in all benchmark designs. Missing metadata, class balance appropriateness, near-duplicate adjudication, provenance, rights and labels still require review. Near-duplicate candidate generation can consume substantial resources on large corpora.

Actual local audit of `tests/benchmark/stage8_ai_writing_synthetic.json`: 2 synthetic records, one declared human and one declared AI; both under 20 words and neither has a declared split; no exact or near duplicates detected. This is a tiny test fixture, not a dataset or evidence of detection quality. No authorized real corpus was found locally or acquired.

### Candidates and restrictions

* [KFUPM Arabic generated abstracts](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts): publisher describes 8,388 method records, original human abstracts and ALLaM, Jais, Llama and GPT-4 variants, including polishing. The academic originals are sourced from Algerian journals; samples share source documents across variants, so all related variants must remain grouped. The [project repository](https://github.com/KFUPM-JRCAI/arabic-text-detection) is MIT-licensed, but a dataset-specific license, redistribution/training grant and original-text rights were not found in the inspected dataset card. Sizes and labels are publisher descriptions, not independent audit. Obtain explicit terms before acquisition/use.
* [ALHD v2](https://zenodo.org/records/22829905): publisher describes over 400,000 human/AI samples across news, social media and reviews from three LLMs; listed files total 4 GB. It is out of academic domain. Available text did not establish a clear license or original-source reuse/derivative-model rights. Label quality and group leakage have not been locally audited. Obtain and check exact release terms and rights before use; at most consider it an out-of-domain challenge set.
* [GRACE academic essay challenge](https://github.com/belgats/gen-ai-detection) describes Arabic and English human/AI essays and seven generators. The repository requests a data-sharing agreement and states ETS essays are restricted to the shared task; no project-specific authorization or independently verified Arabic component permissions are on file. Do not use restricted material without explicit permission.
* The existing Stage 8B audit describes MULTITuDE as a potential CC BY news-domain external test candidate, subject to archive/license/upstream checks, and Ar-APT as lacking verified permission. None is acquired or validated here.

After authorization: obtain versioned files into isolated non-Git staging, retain the grant and restrictions, compute SHA-256, map original labels/provenance and source/prompt/generator groups to the Stage 8B schema without inventing labels, preserve raw text, assign source-group-disjoint train/validation/test partitions, and run:

```powershell
python -m tools.generate_ai_writing_splits INPUT.json SPLIT.json
python -m tools.validate_ai_writing_dataset SPLIT.json --manifest MANIFEST.json
python -m tools.audit_ai_writing_data SPLIT.json --min-words 20
```

Review output, near duplicates and license terms manually; do not treat an exit code as scientific approval. Hold out generators/topics where appropriate, preserve an independent academic test set, include human, AI-polished and mixed writing for evaluation, and use a compatible isolated Python environment. The Stage 8C binary trainer only accepts `HUMAN` and `AI_GENERATED`; mixed/edited samples require a separately designed evaluation rather than relabeling them.

## Environment and deployment

NumPy 2.5.2, SciPy 1.15.2 and scikit-learn 1.6.1 are installed; SciPy reports it requires NumPy <2.5.0. No package was upgraded or downgraded. Resolve versions in an isolated, reproducible environment and rerun the suite before release. No CPU/memory compatibility result for a 4 GB PC has been established. Offline runtime remains unchanged; the future release must bundle and verify any approved model and dependencies, disable runtime downloads, and test both standalone and bounded-concurrency LAN server operation.

## Changed files

`plagiarism_detector/reporting/report_builder.py`, `tests/test_review_history_similarity.py`, `plagiarism_detector/ai_detection/quality_audit.py`, `tools/audit_ai_writing_data.py`, `tests/test_stage8c1_data_quality.py`, and this report. The working tree already contained many other uncommitted changes, which were preserved.
