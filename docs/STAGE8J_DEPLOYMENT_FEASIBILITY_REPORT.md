# Stage 8J — Offline deployment feasibility

## Decision and current stage

**Insufficient evidence to decide 4GB standalone compatibility.** Stage 8J is
deployment feasibility research, not production AI approval. No 4GB/i3 PC was
available. Existing AI detection remains disabled and fail-closed; no model is
declared production-ready. No plagiarism algorithms, review decisions, historical
reports, authentication, or historical release manifests were changed by this stage.

Measured development host: Windows 11, Intel i5-12500H (12 cores/16 logical CPUs),
34,011,582,464 bytes RAM, Python 3.13.2, CPU-only model execution. Research runtime:
Torch 2.9.1+cu128, Transformers 5.3.0, Nawaf INT8 TorchScript from Stage 8H,
two Torch CPU threads, batches of two extracted pages, maximum 512 tokens each.
This CUDA-capable development wheel does not use a GPU in these experiments.

## Method and boundaries

Extended `tests/test_stage8i_full_system.py`, using its isolated temporary database,
real Flask upload/extraction/plagiarism/report persistence route and research-only
inference wrapper. A single upload is extracted once; research inference reuses
those pages and returns the original plagiarism report. Model outputs are discarded;
every successful response retains production AI `unavailable`/`disabled`.

This is a Flask test-client experiment with test authentication/CSRF compatibility
and an antivirus double, not a packaged/network application acceptance test.
Semantic inference is disabled. Despite the settings override, the synchronous
route explicitly permits OCR during extraction; scanned PDF did exercise extraction.
Baseline imports occur before the app-factory timer, so that timer is **not**
complete process startup. Database initialization is outside that timer as well.
Report persistence is timed; report construction is included in plagiarism time.
Individual SQL queries, disk IO, paging, and internal Python import subcomponents
were not independently profiled. No exact retrospective attribution of Stage 8I's
107.51 seconds is possible from its coarse historical measurements.

PDF fixtures: 10/50/100 pages, exactly 100 extracted Arabic whitespace-delimited
words per page (1,000/5,000/10,000 words), 2,136,211/10,680,412/21,362,271 bytes.
They repeat generated text and have far less linguistic/layout diversity than
academic papers. AI input counts: 1,020/5,100/10,200 tokens. One-page image PDF
is rasterized from the digital fixture at 2x resolution. DOCX has ten generated
paragraphs/1,000 words, converted to two extracted pages. Long DOCX pages are
truncated for research AI (931 retained tokens); this is not full-content coverage.

## Cold-start investigation

| Stage (seconds) | Empty baseline | Populated baseline |
|---|---:|---:|
| App factory only | 0.159 | 0.178 |
| First request total | 154.933 | 84.264 |
| PDF extraction | 0.396 | 0.382 |
| Plagiarism/report construction | 5.960 | 8.168 |
| Transformers AutoTokenizer import | 140.764 | 68.043 |
| Thread configuration | 0.00466 | 0.00139 |
| INT8 artifact integrity verification | 0.686 | 0.977 |
| Original source assets integrity verification | 1.788 | 1.961 |
| Tokenizer loading | 0.471 | 0.337 |
| Model file loading | 1.345 | 1.233 |
| Complete research initialization | 145.074 | 72.554 |
| First AI inference | 2.857 | 2.513 |
| Report persistence | 0.044 | 0.023 |

Torch was already imported by the benchmark helper, so its timed import is a
cached near-zero lookup, not a cold Torch import measurement. The dominant measured
first-request delay is importing the tokenizer framework, not reading the model
file. The import varies substantially across fresh processes. These observations
do not isolate disk-cache, antivirus, scheduler or internal import effects, and
the populated run also explicitly sets framework offline environment flags.
Do not interpret their difference as an effect of adding corpus documents.
Request totals include validation/staging and other uninstrumented overhead;
nested timers are not an additive accounting of every operation.

## Empty versus populated corpus

20 generated authorized source fixtures were imported through
`import_reference_paper`, every return value checked for success; import took
0.600 seconds. Sources include a matching repeated passage and other synthetic
source texts. This verifies a populated path, **not** a representative real
academic corpus, large-corpus scaling, or similarity accuracy.

| Workload | Empty request s | Populated request s | Empty plagiarism s | Populated plagiarism s |
|---|---:|---:|---:|---:|
| 10-page PDF, first research initialization | 154.933 | 84.264 | 5.960 | 8.168 |
| 50-page PDF, cached research model | 11.147 | 14.264 | 0.805 | 4.131 |
| 100-page PDF, cached research model | 21.964 | 28.383 | 1.539 | 8.923 |

Warm populated inference took 8.933/17.375 seconds at 50/100 pages. The populated
PDF similarity result was 52.0% versus 0% with no sources. This is an observed
fixture output, not an externally validated expected percentage. Retrieval,
alignment and lexical matcher instrumentation was added for the optimized run;
these nested call timers cannot be subtracted to infer exclusive CPU time.

Populated DOCX returned HTTP 200 in 11.346 seconds (extraction 8.267, plagiarism
0.507, research AI 2.350). Scanned PDF returned HTTP 200 in 3.904 seconds
(extraction 3.333, plagiarism 0.037, AI 0.200), extracting 100 words.
The DOCX run logged **Windows native exception 0x800706be** in Word COM cleanup
(`document_preview_service._convert_with_word`, `word.Quit`). Pytest continued,
wrote results and exited zero. Therefore HTTP success and a passing harness do
not establish stable Word automation. No real-document OCR accuracy was measured.

## Memory findings

| Metric (decimal GB) | Empty baseline | Populated baseline |
|---|---:|---:|
| Peak sampled process-tree working set/RSS | 1.756 | 2.095 |
| Peak sampled process-tree private bytes | 3.203 | 3.621 |
| RSS after releasing model/tokenizer and GC | 1.476 | 1.762 |
| Private bytes at cleanup sample | 2.920 | 3.298 |

Private bytes represent private committed memory, **not physical RAM**. Working
sets include resident shared pages; summing children can double-count shared
memory. Peaks include fixture generation and converter/OCR child processes while
observed; they are not model-only allocations. Sampling is 20 ms and may miss
short-lived processes/allocations. Stage peaks accumulate across requests with
the cached model, rather than measuring per-document incremental allocations.
Python reference cleanup does not return all retained allocator memory to Windows.

The empty run began with 8.609 GB available RAM; populated baseline with 8.436 GB.
Host memory includes unrelated applications. The target runner separately samples
Windows `GetPerformanceInfo` system commit and available physical RAM each second.
These host counters cannot be attributed solely to the application. Page-file IO,
hard faults and browser responsiveness were not measured. A multi-GB private
commit plus Windows, browser, corpus and OCR leaves uncertain 4GB headroom;
development-host success is not proof of either compatibility or inevitable OOM.

## Implemented optimization and safeguards

Added a research-only direct `tokenizers.Tokenizer` adapter for the locally saved,
hash-verified tokenizer JSON. It avoids importing Transformers just to tokenize
already packaged TorchScript inference. It supports only the fixed validated
512-token padded profile and rejects other options. Model/source identity checks,
CPU execution, two-item batches, single cached model and sequential plagiarism/AI
execution remain in place. No production runtime was switched to this adapter.

An opt-in parity test compares all three tensors against AutoTokenizer on empty,
Arabic, mixed-language/diacritized and long truncated inputs in four batch shapes.
This passed, but is finite tokenizer parity evidence, not model accuracy validation.
Targeted checks also cover AI failure isolation and unchanged plagiarism fields.
Lazy loading/caching, sequential execution, existing extraction reuse and cleanup
were already present: this stage does not claim them as newly implemented gains.
No speculative concurrency, model unloading, quantization or batching changes were
made without measurements. Startup prewarming would relocate latency rather than
prove reduced total cost; it is not presented as a measured optimization.

### Measured before/after: populated profile

| Metric | AutoTokenizer baseline | Direct tokenizer |
|---|---:|---:|
| First 10-page request, seconds | 84.264 | 16.509 |
| Complete research initialization, seconds | 72.554 | 4.342 |
| Tokenizer backend import, seconds | 68.043 | 0.030 |
| Tokenizer file load, seconds | 0.337 | 0.119 |
| Model file load, seconds | 1.233 | 1.260 |
| 50-page cached request, seconds | 14.264 | 15.950 |
| 100-page cached request, seconds | 28.383 | 31.133 |
| DOCX cached request, seconds | 11.346 | 10.622 |
| Scanned PDF cached request, seconds | 3.904 | 3.759 |
| Peak tree RSS, decimal GB | 2.095 | 2.000 |
| Peak tree private commit, decimal GB | 3.621 | 3.531 |
| After-cleanup RSS, decimal GB | 1.762 | 1.671 |
| Cleanup private commit, decimal GB | 3.298 | 3.215 |
| Parent process CPU time, seconds | 200.938 | 139.781 |
| Timed fixture/workflow interval, seconds | 147.181 | 83.771 |
| External subprocess wall time, seconds | 166.455 | 104.438 |

The first-request observation improved 80.4%, and initialization 94.0%. There is
no demonstrated warm-inference gain: 50/100-page AI took 9.413/18.764 seconds
versus 8.933/17.375 seconds. Warm request latency increased in this pair of runs.
Additional detailed matcher timing wrappers were present in the optimized run;
other applications, cache state and scheduling were uncontrolled. These are one
fresh-process run per condition, not statistically stable speedups. Small memory
differences are observations, not a proven capacity reduction. Word COM cleanup
exception 0x800706be recurred in the optimized run despite HTTP 200 and exit zero.

Optimized first-request corpus/index access took 7.457 seconds (cached access
0.0014/0.0034 seconds for 50/100 pages). At 100 pages, measured calls accumulated:
shingle candidate retrieval 0.0055 seconds/700 calls; exact matcher 0.3807/600;
lexical matcher 5.0038/700; alignment 2.0049/3,500; report persistence 0.1227.
These timings explain where work occurs in this small fixture; they do not isolate
every database query or establish large-corpus scaling. Similarity values matched
baseline for all workloads (PDFs 52.0%, DOCX 94.7%, scanned PDF 100.0%). Tokenizer
parity is independently checked; matching overall percentages alone is not proof
of complete report equality or external similarity accuracy.

External host samples: baseline/optimized minimum available physical RAM
6.427/6.161 GB; peak total system commit 43.057/43.392 GB against a minimum observed
46.381 GB commit limit. Peak sampled whole-system CPU was 60.4%/61.8%, including
unrelated applications. Parent CPU/elapsed ratios are approximately 1.37/1.67 CPU
cores on average over the timed workflow (child CPU excluded). System commit
exceeds physical RAM on this busy development host; this alone does not measure
active paging or page-file IO. These system figures cannot be projected onto 4GB.

Raw snapshots and pytest logs are preserved in [STAGE8J_EVIDENCE](STAGE8J_EVIDENCE/).
The original empty-run JSON has legacy static limitation strings (including OCR
disabled); the method clarification above supersedes those strings. The inner
test's no-system-commit limitation refers to its own sampler; external `*_host`
files contain separate system-commit measurements. In optimized JSON the retained
legacy key `transformers_import_seconds` times the direct tokenizer backend import.

## Offline standalone and LAN deployment

Use the same Flask/service architecture for both; browser clients need no local
research model on a central offline server. Start target-PC trials with one worker
and one analysis at a time; more workers may duplicate model and corpus caches.
Server queue/concurrency limits must be validated on its own hardware. These are
recommendations, not newly enforced production settings. OCR/Word conversion and
large source collections need separate resource budgeting.

The reproducible runner is `tools/stage8j_target_benchmark.py`; exact transfer,
hash, dependency, command and Performance Monitor instructions are in
[STAGE8J_TARGET_PC_INSTRUCTIONS.md](STAGE8J_TARGET_PC_INSTRUCTIONS.md).
The generated `scratch/stage8j/Stage8J-benchmark-kit.zip` bundles these source
overlays and evidence for transfer, requiring the existing checkout/environment.
An offline wheelhouse/minimal executable was not built. Existing ignored model
files must be explicitly transferred, with original manifests and local OCR assets.
The global development environment has a known NumPy/SciPy compatibility warning;
the earlier isolated baseline environment is not a complete Torch runtime lockfile.

## Remaining scientific and release blockers

No independent authorized Arabic academic evaluation set, academic false-positive
rate, mixed-document performance, AI-polished-human assessment, paragraph accuracy
or AI-percentage error is available. Publisher claims and synthetic fixtures cannot
fill these gaps. Before model approval: settle dataset usage/redistribution rights,
document author/model provenance, independent document-level splits and leakage
checks, calibrate a low-FPR threshold without test-set tuning, and evaluate all
available models on the same held-out conditions using the existing evaluation
pipeline. No new training or redundant dataset pipeline was introduced.

Historical release-integrity evidence must remain unchanged. A known config.py
source-manifest mismatch blocks a fully green regression suite; this stage does
not legitimize it by rewriting hashes. Real corpus coverage, full process-start
import timings, real documents, Word cleanup reliability, page-file activity,
browser responsiveness, actual packaged antivirus/authentication and 4GB hardware
remain necessary before a standalone deployment verdict.

## Tests and evidence

- Empty detailed benchmark: **1 passed**, 21 warnings, 206.14 seconds.
- Populated baseline: **1 passed**, 143 warnings, 156.85 seconds, subprocess exit 0.
- Populated direct tokenizer: **1 passed**, 143 warnings, 94.09 seconds, exit 0.
- Targeted tokenizer parity, AI integration, package integrity and sequence adapter:
  **12 passed**, 19 warnings, 51.95 seconds. The real local parity test was enabled
  with `RUN_STAGE8J_PARITY=1`; it otherwise skips when assets are unavailable.
- Full regression: **895 passed, 2 failed, 2 skipped**, 3,341 warnings,
  494.71 seconds, exit 1. Skips are the opt-in resource benchmark and real-tokenizer
  parity test. Failures:
  - `test_release_manifest_integrity_and_hashes`: unchanged historical config.py
    SHA-256 mismatch, expected
    `ca3c65fde5701d23642497bf3cbab9f3dba65c0d8adfd03acc13bb7b132f492b`, actual
    `22c3e9bfcd2af869abc29f7e7e5ddbc5c1e6c2d1c287387747fbc240a534e548`.
  - `test_cross_process_ocr_crash_recovery`: child exit code was still `None`
    after its five-second ready wait plus five-second join. This failure occurred
    before the assertions testing stale-lock recovery. An **unchanged isolated
    rerun passed**, 11 warnings, 5.93 seconds. This supports startup-timing
    sensitivity, but does not erase the full-suite failure or prove the cause.
    No timeout, assertion, lock logic or historical manifest was changed.

The earlier Stage 8I result was 896 passed/1 failed/1 skipped. The extra skip is
the newly opt-in parity test; the additional observed failure is the OCR child
startup wait. The full suite is not reported as green. Full and isolated rerun
logs are preserved with the benchmark evidence.

Passing benchmark assertions verify report availability, disabled production AI,
successful imports, exactly one extraction and tensor shape. They are not accuracy,
Word automation stability, offline firewall or 4GB acceptance tests. Existing
production AI initialization-failure and unchanged-similarity tests passed in the
targeted group. The experimental benchmark wrapper itself is not a production
runtime failure-recovery implementation; a research model exception fails the
experiment visibly rather than validating a model for production.

## Next development steps

1. Run the supplied harness on the actual 4GB/i3 PC, preserving at least three
   separate cold/warm observations, page-file counters and browser responsiveness.
2. Diagnose Word COM cleanup/RPC exceptions and the OCR child startup timing
   sensitivity before claiming reliable DOCX/OCR deployment.
3. Repeat with an authorized representative academic corpus and real documents;
   measure larger-corpus retrieval, alignment, SQL costs and report persistence.
4. Complete independent low-false-positive AI validation using the existing
   dataset/evaluation tooling and established rights/provenance requirements.
5. Build a clean pinned CPU-only offline environment and wheelhouse, remeasure
   its complete startup/memory, then create fresh release evidence through the
   appropriate release process rather than rewriting historical manifests.
6. Validate bounded LAN queue/concurrency on the intended central server, retaining
   the same application and browser clients. AI remains disabled until validated.
