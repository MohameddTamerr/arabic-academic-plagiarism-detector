# Stage 8L — target-PC validation and offline deployment readiness

## Decisions

| Scenario | Verdict | Evidence gap |
|---|---|---|
| Plagiarism-only standalone on 4GB Windows | NOT VERIFIED | Actual target hardware, packaged workflow and real academic corpus not validated. |
| Application with experimental AI inference | NOT VERIFIED | Target resources and independent academic accuracy/false-positive evaluation are unavailable; production AI remains disabled. |
| Central offline LAN server | NOT VERIFIED | Real multi-client server/load, authentication and hardware tests remain outstanding. |

The accessible host is an HP Victus, Intel i5-12500H, 34,011,582,464 bytes RAM,
Windows 11 Home build 26300. It is not the requested 4GB/i3 machine. No 4GB test
results or academic detector accuracy are claimed. The user confirmed that target
access is unknown and wants weak-device compatibility; an operator procedure is
provided for the actual machine.

## Changes and executable candidate

The Stage 8J workflow runner now offers `--workflow plagiarism` and `--workflow
research`. Plagiarism mode skips the research helper and its Torch import; both
retain the actual plagiarism workflow and disabled production AI status. Research
continues to discard experimental outputs. The low-resource launch script now
supports a separate candidate data directory and sets `SINGLE_EXE_WORKERS=1`.
The frozen executable otherwise defaults to two workers. Six targeted tests cover
normal/default and invalid worker configuration. Synchronous route concurrency is
not globally serialized by this setting.

A separate validation candidate was built from a 5,153-file frozen source snapshot
after code and targeted-test review. The snapshot excludes production databases,
credentials, backups, historical executables and research AI weights. Source
manifest SHA-256: `4a9878f3f172810e1d3cf511a851c0427bf97d54481d6db9a6cdeb66b74be108`.
Candidate: `Arabic-Academic-STAGE8L-Candidate.exe`, 494,156,721 bytes, SHA-256
`4c0309fba8f36915f685a715c6c7c3757bf6ab9e6325251f228d6388bed04a27`, build time
1,240.18 seconds. It is a test candidate, not an approved release. Historical RC3
and its integrity evidence were not replaced. The candidate excludes Torch and
does not provide production AI inference.

All 5,153 frozen inputs were rehashed after the build with **zero mismatches**.
The historical RC3 executable still matches its recorded SHA-256
`905085318d59a5014fa327a5203a71b915bad65734bf942bf36999bf8fb87b72`.
The operator PowerShell launcher was subsequently adjusted to open the normal UI
by default for graceful-shutdown testing; this script is external to the built
executable and differs from the version in the frozen input snapshot.

On the development laptop, a separately launched headless candidate with a new
isolated data directory and `SINGLE_EXE_WORKERS=1` returned HTTP 200 from its local
ping endpoint after **52.223 seconds**. Sampled three-process working-set sum was
346,796,032 bytes and private commit sum 410,132,480 bytes at that single ready
instant; these are not peaks or document-processing measurements. The test-owned
processes were forcibly terminated afterward: graceful shutdown was not tested.
This verifies startup/loopback ping only. It does not verify a browser UI, normal
authentication, uploads, persistence, backup/restore, offline network isolation,
target hardware or sustained resource behavior. The candidate ran on the busy
development host, so the timing is not a 4GB prediction.

A second isolated development-host HTTP probe reached ping in 32.159 seconds.
The root page, normal first-admin setup and login each returned HTTP 200. Generated
PDF, DOCX and scanned-PDF uploads returned HTTP 200 in 3.739, 2.437 and 1.244
seconds respectively, with AI status `unavailable`; a backup request also returned
200. The probe did not independently validate extracted text, OCR accuracy,
similarity, report IDs or backup contents, and the report-ID field it inspected
was absent/null. HTTP 200 is therefore not proof of persistence or correct OCR.
No real representative documents, GUI interaction, restore, network isolation or
graceful shutdown were tested. Test-owned processes were forcibly terminated.

## Measurements and limitations

Prior Stage 8K synthetic development-host tests measured 10/50/100-page PDF
requests at 11.209/11.513/27.903 seconds in one profile run, and 15.483/14.700/
27.692 seconds in another. The latter peak sampled tree working set was 1.988 GB,
private commit 2.579 GB. System commit peaked at 43.798 GB on a busy 34 GB host;
111 whole-system paging samples showed peak pages input 8,665.645/sec, output
0/sec and paging-file occupancy 6.2925–6.2932%. These are not target-PC results,
do not establish application-attributed paging, and omit possible external Word
COM process memory. Those tests used generated documents and a 20-source generated
corpus, Flask test client, antivirus/authentication doubles and semantic-disabled
request settings. They are not executable acceptance or academic accuracy evidence.

Stage 8L additionally ran the new plagiarism-only low-resource test-client mode
on the development laptop: **1 passed**, 145 warnings, 60.37 seconds. The first
10/50/100-page requests took 10.249/6.636/8.916 seconds; DOCX and scanned PDF
took 11.148/3.865 seconds. Peak sampled process-tree working set was 999,342,080
bytes and private commit 1,073,803,264 bytes. It generated one extraction per
upload and production AI stayed unavailable. The prior Stage 8K combined research
run peaked at roughly 1.99 GB / 2.58 GB respectively; these separate single runs
used the same development hardware but differed in time, runtime state and
contention, and are not controlled target-PC or packaged-process comparisons.
Both disabled semantic inference in the benchmark settings. Their difference
cannot establish the resource use of the normal semantic-enabled executable.

Stage 8K real Word probes confirmed original hashes, exclusive file reopening,
deletable outputs and observed Word process exit across three trials; native RPC
diagnostics continued. OCR crash-fixture readiness improved from median 2.721s to
0.126s over five trials each; this is fixture startup, not OCR recognition speed.
The exact Office/RPC cause, long-run leaks and end-to-end hung Word export deadline
remain unresolved.

## Tests and blockers

Targeted Stage 8L tests: **67 passed**, 18 warnings, 7.57 seconds. Full final-source
regression: **907 passed, 1 failed, 5 skipped, 9 errors**, 3,347 warnings, 519.96
seconds. The failure is the preserved historical `config.py` source-manifest hash
mismatch. Nine research-model fixture errors involved incompatible installed
Transformers/Hugging Face modules: missing `validate_typed_dict` and `download_url`.
No manifest or assertion was rewritten. The previous Stage 8K suite result does
not replace the current failed result. A clean, pinned, offline research environment
is required before claiming those tests pass. Current `pip check` also reports
conflicting FastEmbed/Pillow, OpenCV/NumPy and lightecc/pytest requirements.

The candidate requires further normal authentication, antivirus, OCR quality,
report persistence, backup/restore, graceful shutdown, network-isolation and
browser responsiveness acceptance on the target PC. The HTTP checks above are
limited smoke tests. Authorized representative academic documents and a
realistic corpus were not provided. Target-PC results, page-file behavior under
target load, and real document accuracy remain unmeasured.

## Operator procedure and provisional hardware guidance

Use [STAGE8L_OPERATOR_INSTRUCTIONS.md](STAGE8L_OPERATOR_INSTRUCTIONS.md) to record
hardware/page-file settings, verify hashes, run the packaged application with a
new isolated data directory, and perform separate normal and research runs. It
specifies three fresh-process trials and preserving each run's results. Offline
Python dependencies, model assets, local OCR and a complete wheelhouse are not
included in the source overlay. The candidate and research test workload have
different dependencies and resource footprints.

No minimum supported hardware has been established. For planning, 8 GB or more
RAM and an SSD provide more headroom for trials than 4 GB, but neither is a
validated minimum or a compatibility guarantee. Do not purchase or reject a
device based solely on the development-laptop figures; measure the actual
candidate, operating system, browser, OCR and corpus together.

Before enabling AI, obtain authorized Arabic human academic documents, generated
Arabic text with provenance, human/AI mixed paragraph labels and human originals
paired with AI-polished versions; use independent author/document/source splits,
calibrate low false-positive thresholds and evaluate untouched test conditions.

