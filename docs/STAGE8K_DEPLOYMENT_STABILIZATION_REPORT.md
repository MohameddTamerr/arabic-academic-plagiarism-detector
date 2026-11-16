# Stage 8K — Offline weak-PC deployment stabilization

## Verdict: NOT YET VERIFIED

No actual 4GB/i3 Windows PC is accessible in this session. Development-host
success cannot establish weak-PC compatibility. Production AI remains disabled
or no-validated-model, with no experimental percentages in production reports.
No plagiarism algorithms, authentication, authorization, reviewer history,
historical report contents or historical release manifests were changed.

## Word investigation and implemented repairs

Stage 8J logged native Windows RPC diagnostic `0x800706be` during Word `Quit`.
This stage reproduced that output in direct local conversions. The conversion
returned normally, produced a readable PDF and allowed the original DOCX to be
renamed and the output to be deleted. Python-level close/quit failure logging did
not report a raised cleanup exception in those real probes. Word processes were
sometimes visible immediately after return and exited during a bounded grace
period. No process was forcibly terminated by the conversion service.

Distinguish that evidence from a proven interpreter crash or persistent leak:
CPython 3.13.2's Windows fault handler prints its diagnostic and then returns
`EXCEPTION_CONTINUE_SEARCH`, allowing other handlers to run. See the
[version-matched primary source](https://github.com/python/cpython/blob/v3.13.2/Modules/faulthandler.c#L319).
It is an inference that these observed diagnostics are handled native RPC events;
the underlying Office/RPC cause is not established. The diagnostics remain and
have not been suppressed or declared repaired. The Stage 8J interpretation of
the text alone as a cleanup failure was too strong.

Small development-code repairs in `document_preview_service.py`:

- Explicit 64-bit-safe Windows mutex HANDLE signatures; previously ctypes used
  its default integer return convention. Full COM lifecycle remains serialized.
- Release the document COM proxy before Word shutdown; use integer
  `wdDoNotSaveChanges=0`; release the application proxy before COM uninitialization.
- Observe the process obtained from the dispatched Word application's window and
  wait up to five seconds for its exit. Failures are logged visibly. Never kill
  unrelated Word processes; no process-name-wide cleanup is used.
- Close/Quit and temporary-directory cleanup failures now log warnings rather
  than disappearing at debug level or through `ignore_errors=True`.
- Weak references replace the unbounded per-document lock registry. A lifecycle
  test creates 1,000 distinct locks and verifies only a still-referenced lock is
  retained; active callers still share their document lock.
- LibreOffice receives an operation-specific user profile, avoiding reuse of a
  user's running office profile. Its existing 120-second timeout becomes a
  consistent `DocumentPreviewError`, with operation-directory cleanup in `finally`.

Tests cover successful Word lifecycle, export failure, Close/Quit failure,
unconfirmed process shutdown, mutex timeout, LibreOffice timeout, visible cleanup
failure, temporary-file isolation and lock-registry lifecycle. These are mocked
failure cases, complemented by three real Word conversions. Original documents
remain read-only during automation. Existing atomic preview publication and
per-operation temporary filenames are preserved. Persistent cached previews are
intentional cache data, not claimed as temporary-file leaks.

**Remaining Word limitation:** an in-process Office export can still hang; the
mutex wait and shutdown wait do not provide an end-to-end export deadline. A
safe process-isolated converter would require additional packaging/lifecycle
validation. No claim of complete Office stability or repair of native RPC events
is made. Forced thread cancellation and killing a user's Word process were avoided.

## OCR startup investigation

The Stage 8J failure was in a multiprocessing **lock crash fixture**, before
stale-lock recovery assertions, not a measured Tesseract recognition failure.
On Windows spawn, the target's test module imported the application, report
builder, scikit-learn and SciPy before the child could signal readiness.

Three unchanged baseline isolated reruns passed (3.59, 5.80, 3.31 seconds total
pytest times). A controlled five-trial legacy-target run also passed, taking
14.64 seconds total. Moving just the crash fixture to a stdlib-only module
(`tests/ocr_spawn_fixture.py`) removed those child application imports. The
equivalent five-trial run passed in 1.42 seconds total; child readiness ranged
0.119–0.134 seconds. These are test-fixture startup improvements, **not** a claim
that OCR recognition became faster.

The original five-second readiness and five-second exit deadlines are unchanged.
Readiness is now asserted explicitly. A timed-out fixture child is terminated
and joined in `finally` (only that test-created process), preventing test leaks.
The unchanged application recovery assertion still acquires the abandoned lock
within its original five-second limit and checks lock removal on release.
Five trials now run in the full suite as well.

Controlled child-startup ranges: legacy 2.654–2.787 seconds (median 2.721),
minimal fixture 0.119–0.134 seconds (median 0.126). This comparison changes the
fixture import dependency, not the application OCR engine or lock algorithm.

Baseline failure frequency in the new controlled runs was 0/8, optimized 0/5;
there was one historical full-suite timeout in Stage 8J. Small successful samples
cannot prove absence of intermittent failures. The removed import burden is
measured; resource contention as the exact cause of the historical timeout is
plausible but not proven. Tesseract discovery remains locally cached by existing
code; no executable-discovery or OCR scoring algorithm was changed.

A separate diagnostic probe confirmed local Tesseract discovery with Arabic and
English language assets: cold availability check 0.982 seconds, cached lookup
0.0000008 seconds, equal results. This ran alongside regression tests and is not
an isolated throughput benchmark. It establishes working local discovery on this
host, not startup reliability on an older target CPU.

## Measured low-resource workflow: first final-profile run

Development hardware remains Windows 11, i5-12500H, 12 cores/16 logical CPUs,
34,011,582,464 bytes RAM, Python 3.13.2. Model/runtime assets are unchanged from
Stage 8J. All values below are measured observations, not projected 4GB results.

| Workload | Stage 8J direct-tokenizer s | Stage 8K profile s |
|---|---:|---:|
| First 10-page PDF, 1,000 words | 16.509 | 11.209 |
| 50-page PDF, 5,000 words, cached model | 15.950 | 11.513 |
| 100-page PDF, 10,000 words, cached model | 31.133 | 27.903 |
| Generated 1,000-word DOCX | 10.622 | 8.074 |
| One-page, 100-word scanned PDF | 3.759 | 2.406 |
| Repeated DOCX uploads | Not measured | 7.096 / 6.472 |
| Repeated 10-page PDF | Not measured | 3.170 |
| Injected missing research package, report survives | Not measured | 0.924 |

One extraction per normal upload was asserted. Similarity outputs remained
52.0% for digital PDFs, 94.7% for DOCX and 100.0% for the rasterized fixture,
matching Stage 8J. These expected cross-run values are not independently validated
accuracy. All eight normal uploads produced reports with production AI disabled;
the ninth, injected experimental failure also produced a report with AI disabled.

First research initialization took 2.405 seconds, including artifact verification
0.716, source verification 1.107, tokenizer loading 0.038 and model loading 0.538.
First AI inference took 0.795 seconds, warm 50/100-page AI 8.986/17.990 seconds.
Document-length truncation remains: DOCX research input retained 931 tokens;
it is not a complete paragraph-level AI assessment. Corpus import took 0.470
seconds. App factory alone took 0.155 seconds; framework imports and fixture DB
setup precede it. The external subprocess elapsed 100.342 seconds, covering
startup, tests and all workloads; it is not a cold server-start timer.

| Memory, decimal GB | Stage 8J direct | Stage 8K profile |
|---|---:|---:|
| Peak sampled tree working set | 2.000 | 1.990 |
| Peak sampled private commit | 3.531 | 2.581 |
| After-model-release working set | 1.671 | 1.665 |
| Private commit at cleanup sample | 3.215 | 2.251 |

Thread limits are now applied **before** framework imports by the launch profile;
the previous runtime set Torch threads after imports. The observed private-commit
reduction is consistent with less thread/runtime provisioning, but exclusive
allocation causality was not established. Working-set reduction is small.
This compares a combined profile/cleanup change on uncontrolled development
hardware, not isolated proof of each setting's effect. Disk cache and other
applications vary. The profile does not prove 4GB headroom.

Private bytes after the three DOCX uploads were 2.472, 2.497 and 2.497 GB; repeated
DOCX did not show unbounded growth over this short sample. The intervening OCR
request reached 2.508 GB. Model release/GC ended at 2.251 GB private / 1.665 GB RSS;
substantial allocator/corpus/framework memory remains. This is not a long-run
leak test and does not justify claiming no leaks. CPU time was 140.984 seconds
over the 83.103-second inner interval (parent process only).

System samples: minimum available RAM 6.551 GB, peak system commit 46.813 GB,
minimum observed commit limit 50.539 GB, peak whole-system CPU 69.2%. These values
include unrelated processes and the changing Windows page-file policy; they
cannot be projected onto a clean 4GB PC.

**Paging monitor correction:** the first valid profile run reused an existing
CSV name; `typeperf` prompted instead of overwriting, leaving old first-attempt
counter data. Those older timestamps were detected and excluded from this run's
paging results. The runner now uses explicit `-y` and records whether the CSV was
updated during this run and whether the monitor exited prematurely. The fresh
post-regression measurement below verifies the correction; stale data is excluded.

## Low-resource profile and workflow safeguards

`tools/standalone_low_resource.ps1` sets process-local existing scan/OCR/index
limits to one, limits the background scan executor to one through the new optional
`SCAN_EXECUTOR_WORKERS` setting, and sets common CPU library thread limits to two.
Normal defaults are unchanged. It invokes the existing application/server, or
the existing Stage 8J kit with `-Benchmark`. It does not enable AI, disable OCR,
disable essential plagiarism calculations, change report structure or bypass auth.
The benchmark retains its previously documented semantic-disabled research
configuration; this is not presented as full semantic-model memory coverage.

The profile limits queued/background analysis; it does not implement global
admission control across every synchronous route and index/backup operation.
Concurrent direct uploads can still overlap. Start with one operator/one active
analysis; multi-client server limits need separate validation. The same Flask/
SQLite/service architecture remains available for future offline LAN deployment.

Research inference remains lazy, CPU-only, sequential after plagiarism, batches
of two extracted pages, and uses the existing Stage 8J direct local tokenizer and
verified INT8 artifact. It reuses extracted pages. The research benchmark wrapper
now catches and records experimental errors while returning the original
plagiarism report; ordinary benchmark requests assert no hidden research error.
An explicit missing-package injection verifies report availability with production
AI still disabled. Existing package/sequence tests cover missing/corrupt assets.

## Resource measurement boundaries

The existing Stage 8J runner is reused, with an alternate output directory and
Windows `typeperf` sampling for pages input/output per second and paging-file
occupancy. Its monitor is owned by the runner and cleaned up on normal completion
or Python exit. Counter availability must be checked on localized Windows.
Host commit/available physical RAM are sampled each second; the inner benchmark
samples process-tree working set/private bytes at 20 ms and records retained
memory after requests. System counters include unrelated applications. A COM
server started by Windows may not be a Python descendant: process-tree sums do
not necessarily include all Word memory; system counters do include it.

Private committed bytes are not physical RAM. Summed working sets may double-count
shared pages. Short-lived allocations/processes can evade sampling. No separate
allocator attribution for Flask versus SQLite, report construction or retrieval
is available; stage timings and process peaks must not be treated as additive
component memory accounting. Windows/background processes consume additional
RAM. System-wide page-ins are not attributable solely to this application.

## Document/data limits and external validation

The test corpus is 20 authorized generated sources, not a representative real
academic collection. No newly authorized representative academic documents or
actual target PC were available. Workloads reuse the 10/50/100-page generated
Arabic PDFs, generated DOCX and one-page rasterized Arabic PDF from Stage 8J,
plus repeated uploads and an injected research failure. Their success is not
accuracy evidence. Authentication and antivirus remain test doubles in this kit.

On the offline target PC, transfer the existing checkout/environment, verified
local model assets and local Arabic OCR prerequisites per
[Stage 8J instructions](STAGE8J_TARGET_PC_INSTRUCTIONS.md). Then run:

```powershell
powershell -NoProfile -File tools/standalone_low_resource.ps1 -Benchmark
```

Preserve `scratch/stage8k` before each repeat. Record CPU, Windows version, installed
RAM, available RAM before startup, storage type, page-file policy, wall times,
working set, private commit, system commit, paging CSV, crashes and browser
responsiveness. Repeat at least three fresh-process runs. Then validate normal
packaged antivirus/authentication and authorized real documents on the same PC.
No offline dependency wheelhouse or new production release was created here.

Independent Arabic academic AI accuracy remains unverified. Activation requires
authorized human academic writing with documented provenance, independently
generated Arabic AI text with generator metadata, paragraph-labeled mixed
documents, human originals paired with AI-polished versions, held-out document/
author/source splits and leakage checks. Calibrate low false-positive operating
thresholds on validation data, then evaluate untouched test conditions and AI
percentage error using existing tooling. No new training, invented labels or
redundant dataset framework was introduced.

## Final resource rerun with verified-current paging data

After the full suite, the exclusive-open Word/cleanup group passed **13 tests**,
10 warnings, 14.42 seconds. All three original DOCX files could also be opened
using Windows `CreateFileW` with **no sharing permitted**, after observed Word
shutdown; originals retained their SHA-256 and outputs were deletable. The final
resource benchmark then passed **1 test**, 147 warnings, 106.09 seconds, exit 0.

| Final rerun workload | Request seconds | Observed similarity |
|---|---:|---:|
| First 10-page PDF | 15.483 | 52.0% |
| 50-page PDF | 14.700 | 52.0% |
| 100-page PDF | 27.692 | 52.0% |
| DOCX | 9.691 | 94.7% |
| Scanned PDF | 2.988 | 100.0% |
| Repeated DOCX 1 / 2 | 7.415 / 10.250 | 94.7% / 94.7% |
| Repeated 10-page PDF | 2.731 | 52.0% |
| Injected missing-package failure | 0.751 | 52.0% |

The injected failure explicitly asserted one extraction, unchanged overall
similarity versus the first digital PDF, report availability and disabled
production AI. No real model files were deleted or corrupted for injection.

Final sampled peak tree RSS was **1.988 GB**, private commit **2.579 GB**;
after cleanup, RSS **1.666 GB**, private commit **2.267 GB**. Thus the two final
profile observations were approximately 1.99 GB RSS / 2.58 GB private commit;
cold latency varied 11.209–15.483 seconds. Do not select only the faster run or
claim a statistically established speedup. The earlier 3.53 GB private-commit
baseline is substantially higher in these observations, while resident memory
is essentially unchanged. No no-leak or 4GB compatibility conclusion follows.

Fresh host samples: minimum available physical RAM **7.369 GB**, peak system
commit **43.798 GB**, minimum commit limit **50.607 GB**, peak system CPU **61.6%**.
External subprocess wall time was **114.374 seconds**. The paging CSV spans
11:12:37–11:14:29 local time on the test date; **111 valid samples**, current-run
update flag true and monitor still running before intentional stop. Observed
maximum pages input **8,665.645 pages/sec**, pages output **0 pages/sec**, paging
file occupancy **6.2925–6.2932%**. Input counters include file-backed hard-fault
traffic, not solely private-memory page-file reads. These are whole-system
observations on a busy 34 GB development machine, not application-attributed
paging or evidence of a 4GB system's behavior.

The older prompted/stale CSV remains labeled as first-attempt evidence and is
excluded from these final paging figures. No monitor prompt or stale timestamp
was accepted as a successful current measurement.

## Modified files

- `app/services/document_preview_service.py`: COM/resource cleanup, safe HANDLE
  types, weak lock registry, isolated LibreOffice profile and timeout reporting.
- `app/services/scan_service.py`: optional executor worker limit; same default.
- `tests/test_job_management.py`, `tests/ocr_spawn_fixture.py`: lightweight spawn
  target, repeated readiness/recovery verification and fixture-child cleanup.
- `tests/test_stage8k_word_lifecycle.py`, `tests/test_stage8k_real_word.py`:
  mocked failure/lifecycle coverage and opt-in real local Word probes.
- `tests/test_stage8i_full_system.py`: output directory, repeated uploads,
  per-request retained memory, deployment limit metadata and research error isolation.
- `tools/stage8j_target_benchmark.py`: output directory and paging capture lifecycle.
- `tools/standalone_low_resource.ps1`: optional standalone execution profile.
- This report and accompanying Stage 8K evidence.

## Regression results

- Initial cleanup/preview group: **22 passed**, 10 warnings, 1.69 seconds.
- Broader targeted group (real Word, cleanup, preview, AI integration, verified
  model package and sequence adapter): **38 passed**, 19 warnings, 61.46 seconds.
- Final cleanup/real Word group before the added exclusive-open assertion:
  **13 passed**, 10 warnings, 13.64 seconds; three real probes confirmed no observed
  Word process after the shutdown grace period, unchanged originals and deletable
  output PDFs. Native RPC diagnostic text still appeared.
- OCR isolated baselines: **3/3 passed**; controlled legacy **5/5 passed**;
  lightweight fixture **5/5 passed**. Deadlines and recovery assertions preserved.
- Full regression: **910 passed, 1 failed, 5 skipped**, 3,347 warnings,
  396.69 seconds, exit 1. All five OCR recovery trials passed within this run.
  Skips: three opt-in real Word cases, real local tokenizer parity and the resource
  benchmark; their relevant opt-in evidence is recorded separately.

The single failure is `test_release_manifest_integrity_and_hashes`: historical
`config.py` SHA-256 expected
`ca3c65fde5701d23642497bf3cbab9f3dba65c0d8adfd03acc13bb7b132f492b`, actual
`22c3e9bfcd2af869abc29f7e7e5ddbc5c1e6c2d1c287387747fbc240a534e548`.
The development checkout differs from that historical release. Neither its
manifest nor the assertion was changed. The suite is **not** described as green.
The global NumPy 2.5.2 / SciPy 1.15.2 incompatibility warning also remains; a clean
validated dependency lock and offline wheelhouse are still required for deployment.

## Evidence, remaining blockers and recommendation

Raw logs, per-stage/request JSON, host samples, discovery results and paging CSV
are preserved in [STAGE8K_EVIDENCE](STAGE8K_EVIDENCE/). The generated
`scratch/stage8k/Stage8K-benchmark-overlay.zip` contains changed source/tools/tests,
this report and evidence for transfer over the existing checkout. It is **not**
a standalone installer: Python/dependencies, full application, verified model
assets and local OCR must already be transferred per Stage 8J instructions.
The ZIP was checked for archive corruption. No production release was rebuilt.

Recommended next work, in order:

1. Run at least three preserved trials on the actual 4GB/i3 Windows target,
   including normal antivirus/authentication, paging, browser responsiveness and
   authorized real academic documents/corpus. This is an external validation blocker.
2. Establish the remaining Office/RPC origin and validate bounded process-isolated
   conversion if end-to-end Word timeout protection is required. Current evidence
   confirms files/processes released in tested cases, not universal Office stability.
3. Validate admission control for concurrent synchronous/background tasks before
   using the low-resource profile with multiple clients; then benchmark LAN queue
   limits on the intended central server. Keep one application architecture.
4. Build and test a clean, pinned CPU-only offline environment/wheelhouse, resolve
   the NumPy/SciPy incompatibility, and use a new approved release process for
   new integrity evidence. Preserve historical manifests and assertions.
5. Complete authorized independent academic AI evaluation before enabling Check AI.

**Standalone verdict remains NOT YET VERIFIED.** The stage delivered measured
fixture-startup and private-commit improvements, resource lifecycle repairs,
repeated workflow/failure tests and a reproducible target procedure. It does not
claim reliable 4GB operation, validated AI accuracy, a fully repaired native RPC
event source, a long-run no-leak result or a production-ready release.
