# Stage 8H — corrected runtime comparison

## Decision and scope

Fresh-process loading and inference of pre-saved FP32 and INT8 research artifacts succeeded for both models. INT8 reduced runtime RAM and warm time on the development laptop. Neither model is approved for production: independent academic accuracy, acceptable FPR, permitted institutional use, complete-application resource usage, representative 4 GB Windows testing and executable packaging are still unverified. The existing Check AI unavailable status and plagiarism engine were not changed.

## Corrected methodology

`tools/stage8h_runtime.py prepare` loaded the pinned Stage 8F assets, prepared FP32 or oneDNN dynamic INT8, traced a logits-only TorchScript model and saved it with SHA-256, source-checkpoint identity and mode. Preparation processes exited. A separate `run` process verified the artifact and original tokenizer assets, then loaded exactly one artifact. TCP connects were blocked. Each of four variants ran in two fresh Python processes, with three warm workload repetitions in each process. Two CPU threads and batches of two were used consistently.

All variants use the same TorchScript packaging path, rather than comparing eager FP32 against scripted INT8. Trace output matched its eager model on three tested single-example lengths. The exporter emitted tracing warnings; broader batch, padding, shape and token-limit equivalence must be tested before deployment. Artifacts are trusted research files created locally; do not load arbitrary TorchScript files. No original model binary was overwritten.

The load timer excludes initial Python/framework imports, artifact hashing and tokenizer-integrity checks. It measures tokenizer plus model-file loading after those steps. These are fresh-process model-load times, **not total cold application startup or cold disk-cache timings**. Peak and steady-state RSS include loaded framework libraries and inference; conversion is absent. RSS sampling every 20 ms can miss short peaks. CPU seconds and elapsed runtime are saved in each JSON, using the one-core-equivalent convention. No claim is made about operating-system or full application RAM.

## Actual runtime results

Development hardware remains the i5-12500H Windows laptop with approximately 32 GB RAM. Medians below use six warm timings across two fresh processes; ranges show all six. RAM values are medians across the two process runs, in decimal GB. Each workload has exactly 1,000 whitespace-delimited Arabic words in ten repeated synthetic paragraphs. It is not representative academic data.

| Model | Warm median seconds / range | Model load median s | Peak / steady RSS GB | Artifact bytes | Tokens including special tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Primary FP32 | 8.644 / 8.439–8.737 | 0.992 | 1.347 / 1.333 | 541,192,691 | 2,270 |
| Primary INT8 | 4.760 / 4.631–4.838 | 1.454 | 1.198 / 1.188 | 284,795,273 | 2,270 |
| Nawaf FP32 | 4.855 / 4.748–5.275 | 1.002 | 1.332 / 1.323 | 541,190,093 | 1,270 |
| Nawaf INT8 | 2.398 / 2.360–2.557 | 1.458 | 1.183 / 1.183 | 284,793,015 | 1,270 |

The token-count difference is material to comparing models. The INT8 runtime saving is about 0.15 GB here, much smaller than its disk-size reduction because embeddings and framework allocations remain. Stage 8G's conversion-inclusive peaks should not be used as runtime peaks. Full raw results, hashes, trace checks and artifacts are in ignored `scratch/stage8h/`; `summary.json` contains aggregated values. No population-level performance guarantee follows from two processes.

## Quantization behavior and accuracy

On the same five correlated Stage 8F smoke inputs, maximum absolute AI-score change was 0.214206 for the primary and 0.308160 for Nawaf. Using diagnostic argmax at 0.5 only, primary FP32/INT8 disagreed on 1/5 inputs (20%) and Nawaf on 0/5 (0%). The primary flip was on a short human-origin passage with tanween removed. These rates describe only five smoke inputs, including variants of one passage and assistant-generated text. They are not FPR, accuracy, uncertainty estimates or evidence of preserved reliability. Scores are uncalibrated. A zero diagnostic disagreement rate cannot establish zero real-world failures. Score and margin changes can be reproduced from `summary.json`; margin for a two-class output is `abs(2*score-1)`.

Academic accuracy, precision, recall, F1, FPR/FNR, calibration and mixed-document percentage error remain **unmeasured** for all variants. Rechecking [KFUPM](https://huggingface.co/datasets/KFUPM-JRCAI/arabic-generated-abstracts), [GRACE](https://github.com/belgats/gen-ai-detection), and [AIRABIC](https://github.com/Hamed1Hamed/AIRABIC) did not establish an authorized, independently labeled, academic evaluation set for this institution. Evaluation permission is not inferred from training or redistribution permission; relevant terms, original-text rights, label provenance and independence must be recorded separately. Existing institutional files were not repurposed. The Stage 8D.1 permission package remains the acquisition path.

## Application and weak hardware

The complete upload/extraction/plagiarism/AI/report pipeline was **not resource-benchmarked in this stage**. Peak plagiarism memory, overlapping framework allocations, database/worker memory, OS budget and total end-to-end processing time are unmeasured. Existing integration tests check fail-closed behavior and unchanged similarity, but they are not full-application resource measurements. Thus this stage does not resolve the complete-system requirement. No actual i3/4 GB machine was available and no weak-PC compatibility claim is made.

To reproduce on target hardware: copy only a reviewed research artifact, its manifest and matching pinned tokenizer/config assets and hash inventory; install compatible CPU dependencies in an isolated research environment; run `stage8h_runtime run` in new processes without running conversion. Record OS available memory before/after and repeat warm workloads. Separately use an isolated application database and authorized representative PDF/DOCX documents, exercising the authenticated upload workflow while sampling the entire server process tree and OS memory across extraction, plagiarism, sequential AI and report stages. Retain source hashes, page/token/word counts, failures and timings. Do not activate production inference to perform that experiment.

## Research packaging and tests

Artifacts load locally with no conversion, network or cloud service. Mode, source identity and file hash are checked. Tests reject wrong-source, wrong-mode, corrupt and missing packages. This is a Python research packaging test, not PyInstaller/EXE validation. TorchScript tracing and quantization deprecations, the existing NumPy/SciPy warning and platform/runtime-version compatibility remain release concerns. Historical executable and release manifests were not modified.

Targeted command: `python -m pytest -q --disable-warnings tests/test_stage8h_package.py tests/test_sequence_research.py tests/test_ai_analysis_integration.py tests/test_review_history_similarity.py`: **17 passed, 0 failed, 0 skipped**, 19 warnings, 21.98 s. Synthetic unit fixtures verify behavior, not detector accuracy. Full-suite result is recorded when available.

Full current-source command `python -m pytest -q --disable-warnings`: **896 passed, 1 failed, 0 skipped**, 3,343 warnings, 438.75 s. The sole failure remains the historical source-manifest hash mismatch for development `config.py`. The test and historical manifest were preserved. No passing full-suite or production-readiness claim is made.

Files added: `tools/stage8h_runtime.py`, `tests/test_stage8h_package.py`, this report; research artifacts under ignored scratch. Recommendation: Nawaf INT8 is the fastest measured research variant for this workload only. Neither candidate is selected for production; independent academic and complete-system validation take precedence over this performance ranking.
