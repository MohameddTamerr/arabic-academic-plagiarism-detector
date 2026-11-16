# Windows 8 GB release candidate

## Release checklist

- [x] Audit the working tree, Windows build inputs, workflow entry points and existing AI adapters.
- [x] Keep the production AI gate closed and verify that an AI error leaves plagiarism evidence and report persistence available.
- [x] Exercise the local model path and evaluation accounting with code-path fixtures. Record real inference timings separately from authorship metrics.
- [x] Compare CAMeL Tools on extracted Arabic pages and run the existing normalization and highlight regressions.
- [x] Build the executable side by side and verify its independent release manifest and checksum.
- [ ] Reconcile the historical root source-manifest check if a clean default suite is a promotion requirement.
- [ ] Run the packaged candidate on an isolated 8 GB Windows system with operational antivirus, representative corpus size, OCR, DOCX preview and the shutdown workflow.
- [ ] Approve a rights-cleared, independent Arabic academic test set and accepted false-positive and coverage criteria before deploying AI inference.

## Analyze API

`POST /api/analyze` returns a saved report. `POST /api/scan` and `POST /api/analyze_async` retain their queue responses. Poll `GET /api/tasks/<task_id>` and read the fields below under `result` when the task completes. The combined thesis workflow keeps its existing upload, job and report routes.

| Field | Contract |
| --- | --- |
| `plagiarism_analysis.status` | `completed` for a completed analysis, or `partial` for a combined thesis with incomplete parts. Task errors keep the existing task-level status and error. |
| Plagiarism evidence | Existing top-level scores, `segments`, and `sources` remain available. Report evidence is available at `GET /api/reports/<id>/evidence`, with existing pagination and access rules. |
| `ai_analysis.status` | `unavailable` in the current release. |
| `ai_analysis.validation_status` | `no_validated_model`, including when the experimental setting is off. |
| `ai_analysis.reason` | `disabled` for the existing default, `no_validated_model` if the experimental setting is enabled, or `analysis_error` if the AI integration fails. |
| AI evidence | `paragraphs: []`, `model: null`, all four percentage fields `null`, and an Arabic `limitations` message. |

`GET /api/reports/<id>` and `GET /api/reports/<id>/summary` expose both statuses. Full and summary reads present historical heuristic AI values as unavailable. Stored reports and integrity snapshots retain their original contents. Combined thesis reports carry each included part's AI status and a combined unavailable status. An AI `analysis_error` leaves the completed similarity result, evidence and saved report usable.

## Offline AI evaluation

The bundled ONNX INT8 model is the multilingual E5 similarity encoder. The AI research candidates use local BERT checkpoints or pinned TorchScript graphs. The production report builder imports only the unavailable response. It loads no research model or model dependencies.

`iter_paragraphs(raw_text, pages)` gives the research adapters source spans. It splits at blank lines and retains single line breaks, punctuation, diacritics and whitespace within each span. Offsets are zero-based Python Unicode character indexes with an exclusive end. Page offsets index the supplied page record or raw text. Document offsets index the concatenation of nonempty supplied page texts with `\n\n` between them. `page_index`, `page_number`, `file_index` and `source_file` distinguish repeated page numbers across files. OCR-derived text is identified when that metadata is present. These offsets address the extracted strings. PDF coordinates still come from the established highlight path.

Use an isolated CPU research Python environment with installed PyTorch, Transformers, Tokenizers and their local dependencies. Start with the provenance fields and split tooling in [the dataset spec](../STAGE8_DATASET_SPEC.md). Use the complete declared split file so document, author and prompt groups can be checked across splits. The authorization manifest needs these fields.

| Field | Required value |
| --- | --- |
| `dataset_use_authorized`, `model_use_authorized`, `independent_evaluation_attested` | `true` with documented approvals and split independence |
| `dataset_authorization_reference`, `model_authorization_reference` | References to the applicable permissions |
| `data_sha256` | SHA-256 of the exact UTF-8 split file |
| `human_threshold`, `ai_threshold`, `threshold_reference` | Predeclared numeric thresholds in ascending order within `[0, 1]`, with a reference to the separate threshold-selection protocol |

```powershell
python -m tools.evaluate_sequence_research `
  --data .\authorized\splits.json --manifest .\authorized\evaluation-approval.json `
  --model-dir .\research\checkpoint --file-hashes .\research\trusted-hashes.json `
  --class-one AI_GENERATED --mapping-evidence 'Reference to the verified model label mapping' `
  --threads 2 --batch-size 2 --output .\authorized\evaluation-result.json
```

For the matching INT8 artifact, append `--artifact .\research\classifier.jit --artifact-mode int8 --artifact-manifest-sha256 <trusted-manifest-hash>`. The pinned `classifier.manifest.json` must be adjacent to the graph and bind the graph hash, mode and original checkpoint digest. Use only a graph from a trusted source. Tokenizer and configuration assets remain pinned in the file hash inventory. The process loads one CPU model on demand and processes batches sequentially.

The result contains aggregate confusion counts, class coverage, abstentions and covered/all-sample false-positive and false-negative rates. Truncated or oversized inputs abstain. Edited and mixed provenance classes are counted separately from the binary metrics. Outputs include model, runtime and input hashes without paragraph text or per-record scores. Attestations and duplicate checks support an evaluation audit. Reviewer assessment of annotation provenance, distribution and generalization is still required.

## Packaging on the build workstation

Use Windows AMD64 CPython 3.13 with this checkout's vendored native libraries, local E5 and OCR assets, and the working PyInstaller build environment. The build reuses the repository's single-executable spec generator. A target machine runs the executable without Python. Keep production data outside the build and smoke-test directories.

```powershell
$env:PYTHONUTF8 = '1'
$candidate = Join-Path $PWD 'scratch\win8-final-candidate'
python -m tools.package_windows_candidate $candidate
if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed' }
$exe = Join-Path $candidate 'Arabic-Plagiarism-System-Windows8GB-RC.exe'
python -m tools.verify_release_provenance $exe `
  (Join-Path $candidate 'RELEASE_MANIFEST.json') (Join-Path $candidate 'SHA256SUMS.txt')
if ($LASTEXITCODE -ne 0) { throw 'Candidate verification failed' }
```

Choose a fresh candidate directory on each build. Retain its `source/STAGE8L_SOURCE_MANIFEST.json` and the two sidecar files as build evidence. For a local 8 GB acceptance run, use the existing one-worker profile with a new data directory and an unused port. The command below opens the normal launcher.

```powershell
powershell -NoProfile -File .\tools\standalone_low_resource.ps1 `
  -Candidate $exe -DataDirectory (Join-Path $env:TEMP ('baba-win8-' + [guid]::NewGuid())) -Port 5058
```

## CAMeL Tools decision

CAMeL Tools 1.6.0 ran from an isolated wheel installation with no morphology or disambiguation assets. Across 25 extracted Arabic pages and seven repeats, median offset-preserving tokenization was 45.02 ms with CAMeL and 29.26 ms with the existing alignment tokenizer. CAMeL with offset reconstruction and the same downstream aggressive normalization differed on 23 pages. Its light normalization primitives took 3.16 ms versus 9.20 ms for the existing implementation and produced different strings on all 25 pages. The smaller operation set retained tatweel and zero-width characters on targeted probes. The comparison establishes compatibility and timing differences. It provides no measured plagiarism-quality gain. The release uses the existing preprocessing. [CAMeL Tools tokenizer API](https://camel-tools.readthedocs.io/en/latest/api/tokenizers/word.html)

## Windows development-host measurements

Windows 11 build 26300, Intel Core i5-12500H, 16 logical processors, 31.68 GiB physical RAM, CPython 3.13.2. The source E5 INT8 session returned `CPUExecutionProvider` and produced a 384-dimensional embedding with socket connects blocked. The AI research benchmark also blocked socket connects. It used one TorchScript model per fresh process, PyTorch 2.8.0, Transformers 4.57.6, two CPU threads and batches of two. Other development tasks ran on the same workstation during these measurements.

| Research model | Cold import and verified load | Peak working set / sampled private bytes | 1-page PDF first / warm median | 24-page PDF excerpt first / warm median | Inference errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| INT8 | 15.15 s | 949.4 / 1,235.4 MiB | 1.07 / 0.62 s | 26.61 / 21.19 s | 0 |
| FP32 | 15.13 s | 1,047.2 / 1,207.2 MiB | 1.29 / 1.03 s | 44.68 / 43.83 s | 0 |

The two inputs contained 352 and 12,201 extracted words across 12 and 227 blank-line-delimited spans. Each warm median uses three repeats after the first inference on that input. The 24-page first inference reused the model warmed by the single-page input. Neither artifact truncated a span in these samples. The samples carry no evaluation labels. No scores were retained. These timings and peaks apply to the separate research process and the indicated workload. The packaged production classifier remains unavailable.

The packaged E5 run used one worker, local Windows Defender, loopback HTTP, one seeded reference, and OCR off for the native PDFs. A fresh launch took **37.35 s**. The one-page PDF completed in **4.98 s** on the first scan and **0.79 s** and **0.78 s** on repeat scans. The reopened report returned one evidence item and one highlight rectangle. The 568-page thesis extracted in **8.27 s**, then exceeded the probe's **310 s** end-to-end deadline during similarity analysis. Sampled peak process-tree working set was **1,068.2 MiB** and sampled private memory was **1,108.5 MiB**. No non-loopback TCP peers were observed by the periodic process-tree sampling. The probe stopped its isolated process tree after the timeout, and SQLite integrity passed.

On the same workload, a fresh one-worker run with `enable_semantic_model: false` started in **25.99 s**. The one-page PDF took **1.52 s** on its first scan and **0.35 s** and **0.37 s** on repeat scans. The 568-page, 263,268-word thesis completed in **297.70 s**, including **7.95 s** for extraction and **286.00 s** for similarity analysis. A source cProfile run on 24 pages spent **16.69 s of 19.54 s** in the lexical TF-IDF matcher across **854** calls. This points to per-query vectorizer fits as a remaining large-document performance cost even with E5 off. The release keeps the existing similarity behavior and profile choices.

The lexical run also completed a generated DOCX in **10.45 s** with preview HTTP 200 and a rasterized Arabic OCR smoke input in **3.03 s**. Neither exercise used authorship or OCR accuracy labels. Report summaries reopened, logout denied access with HTTP 401, a report reopened after restart, and SQLite integrity passed. There were zero scan errors. Sampled process-tree peaks were **731.2 MiB working set** and **770.7 MiB private memory**, excluding any service process outside the application tree. There were no sampled non-loopback peers. The probe used forced cleanup of its own processes and does not establish graceful packaged shutdown. Target 8 GB acceptance still needs an actual offline target host and a representative reference corpus.

The development measurements and scripts are in `scratch/release-8gb-camel/`. `package-results-a.json` records the E5 run, `package-results-lexical.json` records the lexical run, and `int8-results.json`, `fp32-results.json`, and `camel-results.json` record the separate experiments. The package probe takes the executable, a fresh data directory and a fresh results path. Add `--lexical-only` to select the lexical run. The scratch logs contain no labels or AI scores from the research benchmark.

## Test and build evidence

- Initial full suite on this checkout reported 931 passed, 3 failed, 9 setup errors and 5 skipped. The setup errors came from the BertTokenizer fixture constructor on Transformers 4.57.6. The backup test depended on native Word conversion. The thesis test inherited a process-wide scan executor closed by shutdown tests.
- Final full suite reported **949 passed, 1 failed, 5 skipped, 0 setup errors**. The remaining failure compares the current `config.py` to the historical root `release_manifest.json`. The historical `FINAL_RELEASE` RC3 artifact still verified against its own sidecars. The new candidate's 42 critical file hashes matched its frozen source, and the executable verified against its new sidecars.
- The suite skipped an opt-in real-model harness, a tokenizer asset probe and three native Word runs. The focused suite recorded 70 passes, and the isolated shutdown and thesis sequence recorded 14 passes. The backup integration test uses a local converter fixture that reads the original DOCX. Native Word remains a separate acceptance check.
- The Windows candidate is `scratch/win8-rc2/Arabic-Plagiarism-System-Windows8GB-RC.exe`, 494,147,499 bytes, SHA-256 `6307f628b929d3a7840f59b71df85578ef997e6f6cf69e66d0f2f0b27ca66dad`. The archive contains the E5 ONNX INT8 similarity encoder and Arabic/English OCR assets. Archive inspection found zero Torch or TensorFlow modules and zero authorship model binaries.

## Changed repository files

- API and reporting changes span `app/repositories/report_repo.py`, `app/routes/report_routes.py`, `app/services/thesis_service.py` and `plagiarism_detector/reporting/report_builder.py`.
- AI changes span `analysis.py`, `paragraphs.py`, `pretrained_research.py` and `sequence_research.py` under `plagiarism_detector/ai_detection/`, plus `tools/evaluate_sequence_research.py` and `tools/stage8h_runtime.py`.
- Packaging changes span `tools/build_single_exe.py`, `tools/stage8l_freeze_candidate.py` and `tools/package_windows_candidate.py`.
- Test changes span `tests/test_ai_analysis_integration.py`, `tests/test_evaluate_sequence_research.py`, `tests/test_pretrained_research.py`, `tests/test_sequence_research.py`, `tests/test_stage8m_backup_sources.py` and `tests/test_stage8m_shutdown.py`.
- The release checklist and API instructions are in `docs/WINDOWS_8GB_RELEASE.md`.
