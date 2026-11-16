# Stage 8D — real model training and data status

## Decision

No real dataset was acquired, no real classifier was trained, and no model was selected or enabled. The available documentation does not establish the institutional training, retention, derivative-model and upstream-text rights required for the candidates; public availability alone is not sufficient. The original application stays offline and retains its fail-closed AI status. This stage implements an independently useful, research-only importer for institution-authorized text and tests it on explicitly synthetic fixtures. It does not read institutional documents or assign human/AI labels itself.

## Candidate evidence and acquisition

| Candidate | Source, data and suitability | Rights and decision |
| --- | --- | --- |
| KFUPM Arabic generated abstracts | [Publisher card](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts), API revision `584e43a346914a4cb1a51f9679f903284b65c36e` observed 2026-11-05. Publisher describes 8,388 method records from academic abstracts, including original human abstracts and ALLaM, Jais, Llama and GPT-4 variants; title-only, title+content and polishing methods share sources. These counts and labels are not independently audited. | Dataset API exposes no license field. The [code repository](https://github.com/KFUPM-JRCAI/arabic-text-detection) has an MIT license; its applicability to dataset records and upstream Algerian journal abstracts is not established. Request written dataset, underlying-text, training, retention, derivative-model and institutional-use terms from dataset owners and applicable rights holders. No acquisition. |
| GRACE Arabic essays | [Shared-task project](https://github.com/belgats/gen-ai-detection) describes human/AI essays and a seven-generator task; Arabic-specific provenance and permissions need separate verification. | Project requests a consent form and states ETS essays are restricted to the shared task. Do not infer permission for institutional model training. No acquisition. |
| ALHD v2 | [Zenodo record 22829905](https://zenodo.org/records/22829905): publisher describes over 400k samples, three generator families, news/social media/reviews, 4 GB of listed files. Not an academic benchmark. | On 2026-11-05 the record API returned null license/rights fields; underlying-source rights and training terms are unverified. Seek documented terms. No acquisition. |
| Ar-APT | [Research article](https://doi.org/10.1186/s40537-026-01492-8) describes 16,400 records from human articles and AI polishing; useful for false-positive evaluation, not a complete academic corpus. | [Dataset repository](https://github.com/Saleh-Almohaimeed/Ar-APT) provides no verified dataset and original-text usage grant in this review. Obtain terms before use. No acquisition. |
| Institution-owned material | Could provide actual academic domain and known sources. | Import only after the institution documents permission to process originals, create/store generated derivatives, train/evaluate, retain and deploy the resulting model; labels and author provenance must be independently established. No such material was imported. |

No real dataset statistics, legal authorization, duplicate rate, label quality or independent academic evaluation have been verified. Do not confuse publisher-reported metadata with a local audit. No external messages were sent.

## Authorized local preparation

`tools/prepare_authorized_ai_data.py` accepts a UTF-8 JSON array of explicitly labeled Stage 8 records and an acquired manifest containing explicit permission and an authorization reference. Each record requires an explicit `source_document_id`; human originals, AI variants and polished variants of one source must share it. Existing group-based splitting operates over connected document/source/author/prompt groups, assigns them together and preserves original Unicode text and supplied provenance labels. The importer rejects already assigned splits rather than silently replacing a locked split. Mixed records require explicitly provided, non-overlapping labeled original-text offsets; no model infers labels. The importer writes a new output file exclusively and prints input SHA-256 and seed. Output remains `prepared_not_validated`: metadata is asserted by the curator, not independently proven.

Example after authorization, using isolated non-Git staging:

```powershell
python -m tools.prepare_authorized_ai_data INPUT.json MANIFEST.json SPLIT.json --seed stage8d-v1
python -m tools.validate_ai_writing_dataset SPLIT.json --manifest MANIFEST.json
python -m tools.audit_ai_writing_data SPLIT.json --min-words 20
```

See `plagiarism_detector/ai_detection/dataset.py` for required record fields and `plagiarism_detector/ai_detection/provenance.py` for manifest fields. The manifest additionally requires `research_use_authorized: true` and a nonempty `authorization_reference`. Curators must retain the actual permission documents separately and supply genuine source IDs, labels, generator and editing provenance. Review short/empty/non-Arabic text, encoding, balance, exact and near duplicates, topic/source/generator overlap and labels. Existing near-duplicate detection may be expensive for a large corpus. Splits do not guarantee balance, independent topic/generator holdout, absence of unknown duplicates, or a sufficient number of examples. Review those conditions before locking the test set. The existing binary baseline rejects mixed/polished labels; keep these for separately designed evaluation, preserving their source group and never relabeling them as fully generated. Stage 8C tools do not enforce one-time test use; record and freeze model selection and threshold before accessing the final test.

## Training, evaluation and model comparison

No real baseline artifact, accuracy, FPR/FNR, subgroup performance, calibration, mixed-document percentage error, inference time or memory measurement exists for this stage. Tests use explicitly synthetic examples only. The local E5 model is a retrieval model, not an AI-authorship classifier. Advanced models were not downloaded or selected before a real baseline.

| Model | Accuracy | Precision | Recall | F1 | FPR | CPU speed | Peak RAM | Disk size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TF-IDF + logistic regression | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | No real model |
| TF-IDF + linear SVM | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | No real model |
| Farras | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not installed |
| Fine-tuned AraBERT | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not installed |
| Quantized classifier | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Unmeasured | Not installed |

Neither a production model nor an AI percentage, paragraph prediction or highlight is available. A model must first meet independent academic-domain, human false-positive and mixed-document evaluation criteria; then measure full-application CPU/RAM on an actual 4 GB Windows PC and validate offline packaging before an opt-in integration. The current desktop and future bounded-concurrency LAN backend remain unchanged.

## Dependency environment

The original environment has Python 3.13.2, NumPy 2.5.2, SciPy 1.15.2, scikit-learn 1.6.1 and a SciPy warning requiring NumPy <2.5. A separate ignored `.venv-stage8d` was created with the exact direct packages in `requirements-stage8d-research.txt`: NumPy 2.2.6, SciPy 1.15.2, scikit-learn 1.6.1, joblib 1.5.1 and threadpoolctl 3.6.0. `pip check` returned `No broken requirements found`; both baseline implementations fitted, calibrated and evaluated a synthetic fixture under `python -W error` without the compatibility warning. These are software smoke tests, not model validation or application compatibility tests. This requirements list is not a hash-locked production release or a complete Flask environment. The production environment was not changed.

## Tests

Targeted current-environment command `python -m pytest -q --disable-warnings tests/test_stage8d_preparation.py tests/test_stage8c_baseline.py tests/test_stage8b_dataset_validation.py tests/test_stage8c1_data_quality.py tests/test_ai_analysis_integration.py tests/test_review_history_similarity.py`: **37 passed**, 133 warnings, 11.81 seconds. The tests verify explicit permission/source requirements, linked variants, preservation of supplied labels/text, mixed-span checks, existing group/leakage tests, training/calibration fixture tests, offline behavior, and similarity regression tests. They do not test real dataset loading or actual model accuracy. Full-suite result is recorded below.

Full command `python -m pytest -q --disable-warnings` before the final locked-split safeguard: **882 passed, 1 failed, 0 skipped**, 3,402 warnings, 257.43 seconds. The sole failure is `test_release_manifest_integrity_and_hashes`, because current development `config.py` does not match the historical root source manifest. The strict test and historical release evidence were not modified. The full suite used the original Python environment, not the isolated research venv; warnings include the original NumPy/SciPy incompatibility, deprecations and a libpng CRC warning. Prior separate RC3 artifact/manifest/checksum verification is documented in the Stage 8C.1 report; it does not certify this source checkout or the new work. The final safeguard was verified separately as recorded below.

After adding the locked-split safeguard, the targeted command above was rerun: **38 passed, 0 failed, 0 skipped**, 133 warnings, 8.82 seconds. The full suite was not repeated after this last change.

## Next action

Obtain a project-specific written grant for an academic corpus and underlying texts or authorized institutional source material, then import and independently audit it, curate source-linked splits and a locked academic test set with edited/mixed evaluation cases, and train/evaluate the existing two research baselines. Resolve the full application's dependency environment in an isolated test build. Measure target-machine performance and prepare offline, hash-verified artifacts only after scientific and operational acceptance. Preserve historical release manifests; the prior full-suite source-manifest failure concerns the development tree differing from the frozen manifest, not proof that RC3's executable checksum is wrong.
