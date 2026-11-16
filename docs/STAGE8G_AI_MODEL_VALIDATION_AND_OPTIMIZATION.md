# Stage 8G — research validation and CPU optimization

## Decision

Both candidates remain rejected for production approval pending independent academic evaluation, permitted institutional use, target-hardware and packaging checks. No accuracy, F1, FPR/FNR, calibration or mixed-document percentage error was measured. No validated minimum input length exists. All research decisions now explicitly say `INSUFFICIENT_EVIDENCE`, while raw scores remain available for experiments. Production and plagiarism calculations were not modified.

## Inputs and scientific limitations

The exact Stage 8F checkpoints and hash inventories were reused; no duplicate downloads. Both are binary BERT sequence classifiers with a 768-to-2 head, maximum 512 tokens. The primary's card and `model_info.json` identify 0=human, 1=AI; the alternative embeds the same meaning in configuration. The primary card supplies original text directly; no aggressive normalization was applied. Hashes, versions and source links are preserved in `STAGE8F_REAL_PRETRAINED_MODEL_REPORT.md`.

No authorized independent academic dataset was supplied or found locally. KFUPM data still lacks established project-use terms; GRACE access and component restrictions require review. AIRABIC declares CC BY but includes inconsistent ShareAlike wording and underlying books/news whose rights and independence from these models are unverified. Existing institutional PDFs are not automatically authorized for evaluation or verified human-authored. Model cards declare Apache-2.0, which does not settle upstream training-data rights. No new corpus was acquired. The same five Stage 8F smoke inputs were used for both models; these include one short UN-origin excerpt, two related variants, and two assistant-generated passages. They cannot establish accuracy, FPR, calibration, academic-domain performance or a supported length threshold.

## Measured comparison

Windows development laptop: i5-12500H, about 32 GB RAM, CPU-only inference, two CPU threads, batches of two. New processes were used for each variant, TCP connections were blocked, and the same repeated synthetic 1,000-word workload ran three times. Values below are medians; primary FP32 times ranged from 3.96 to 8.48 seconds, demonstrating timing variability. Accuracy/F1/FPR are **unmeasured for every row**.

| Variant | Median seconds/1,000 synthetic words | Sampled peak process RSS bytes | Weight/state bytes |
| --- | ---: | ---: | ---: |
| Primary FP32 | 8.167 | 1,178,976,256 | 540,803,072 |
| Primary dynamic INT8 | 4.651 | 1,576,816,640 | 284,338,885 |
| Nawaf FP32 | 4.687 | 1,157,083,136 | 540,803,072 |
| Nawaf dynamic INT8 | 2.491 | 1,561,911,296 | 284,338,885 |

INT8 uses the existing PyTorch oneDNN backend and quantizes Linear modules; embeddings remain FP32. The first attempt failed because FBGEMM was unavailable. Backend selection was corrected to choose an installed backend. Conversion took 1.19 s (primary) and 1.72 s (alternative). Peak RSS includes loading and conversion, not a standalone pre-quantized reload, so it cannot demonstrate reduced deployment RAM. State-dict byte sizes are not directly equivalent to a production Safetensors package; research `.pt` artifacts must not be loaded from untrusted sources. PyTorch emits a quantization deprecation warning. Raw results and state dicts are under ignored `scratch/stage8g/`.

Primary maximum absolute smoke AI-score drift was approximately 0.2142, and alternative drift approximately 0.3151. This is substantial; neither INT8 variant is accepted for integration despite faster synthetic inference and smaller serialized state. Drift on five inputs cannot measure accuracy loss or safety. No classification threshold or minimum length was inferred from these scores.

## Synthetic document measurements

Primary FP32 actually processed synthetic workloads with 250 repeated words/page, two 125-word paragraphs per page: 10 pages (2,500 words), 21.46 s; 50 pages (12,500 words), 89.84 s; 100 pages (25,000 words), 209.17 s. No paragraphs were truncated. These are not extracted real documents or full Flask analysis times. Cold primary load including hashing was 48.81 s; alternative FP32 load was 52.74 s. Initial framework imports precede this timer. Primary process CPU across the complete run was 184.4% using a one-core-equivalent convention; 100% means one fully occupied core. RSS was sampled every 50 ms and may miss short peaks.

Optimized and alternative page-scale workloads, full-application memory/latency, and actual 4 GB Windows hardware were not measured. ONNX/ONNX Runtime are installed, but no export or ONNX inference experiment was performed; no benefit is claimed. Duplicate tokenization remains in the adapter to preserve exact truncation reporting; no speedup from removing it is claimed. The current evidence supports neither weak-PC compatibility nor choosing the faster model as reliable.

## Changes and usage

`tools/stage8g_cpu_experiment.py` adds reproducible FP32/INT8 timing, CPU/RSS sampling, optional synthetic page workloads and research-state serialization. Existing model directories and hash manifests are mandatory. `SequenceResearchAdapter.close()` releases its model/tokenizer references; tests verify that the model object is released and that loading works again. This does not guarantee immediate RSS reduction because allocators may retain memory. The adapter now emits explicit `INSUFFICIENT_EVIDENCE` decision status for all unvalidated research outputs. No production inference or AI document percentage was enabled, and no simultaneous production-model lifecycle was introduced.

Example: `python -m tools.stage8g_cpu_experiment --model-dir scratch/stage8f/nawaf --hashes scratch/stage8f/hashes_nawaf.json --smoke scratch/stage8f/smoke.json --mode fp32 --output NEW_RESULTS.json --threads 2 --batch-size 2 --repeats 3`. Use `--pages 10 50 100` for explicitly synthetic page tests. Output files are created exclusively. INT8 remains an experimental rejected variant.

## Tests and next steps

Targeted command: `python -m pytest -q --disable-warnings tests/test_sequence_research.py tests/test_ai_analysis_integration.py tests/test_review_history_similarity.py tests/test_span_aligner.py` — 21 passed, 19 warnings in 37.68 s. This includes synthetic checkpoint tests, offline loading, labels, truncation, lifecycle cleanup, fail-closed behavior and existing similarity regressions. It is not independent model validation. The original NumPy/SciPy compatibility issue remains; no dependencies were changed.

Full current-source run: `python -m pytest -q --disable-warnings` — **894 passed, 1 failed, 0 skipped**, 3,344 warnings in 446.27 s. The sole failure is the existing historical source-manifest hash mismatch for development `config.py`; no historical manifest or integrity assertion was changed. Modified files in this stage: `sequence_research.py`, `tests/test_sequence_research.py`, new `tools/stage8g_cpu_experiment.py`, and this report. No production AI or plagiarism configuration changed.

Obtain a rights-cleared academic evaluation set with independent sources, separate threshold/calibration and locked test sets, human/polished/mixed/OCR examples and multiple domains/generators. Evaluate FPR with uncertainty and subgroup counts before choosing any model or length rule. Investigate ONNX and quantization only with output-drift checks and independent accuracy evaluation; measure the full application on target hardware. Current recommendation: preserve production-disabled status for both candidates.
