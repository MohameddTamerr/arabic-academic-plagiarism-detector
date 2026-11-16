# Stage 8L: actual target-PC acceptance procedure

This package does not certify 4GB operation. Record results on the actual older
CPU/4GB Windows machine. Never use the historical RC3 executable as the new
candidate, replace its installation, or reuse production data for these trials.

## Transfer and preflight

Transfer the side-by-side candidate executable, its SHA-256 artifact record and
source manifest, this checkout/tools (or source overlay), and existing local OCR
installation/Arabic assets. For Python research tests additionally transfer a
compatible offline Python environment and verified Stage 8F/8H local assets per
the Stage 8J instructions. The candidate excludes Torch/research AI; the research
workload is a separate Python experiment. No runtime downloads or cloud services
are allowed. No complete wheelhouse is supplied by the source overlay.

Verify every transferred manifest file with SHA-256. A missing candidate or
checksum mismatch blocks executable acceptance. Install the candidate in a new
folder and use a new empty data directory. Confirm local antivirus and document
converter/OCR prerequisites; do not use test doubles in executable acceptance.
Disconnect external networking while retaining loopback; record how this was done.

Record the document list before testing: path, SHA-256, authorization basis,
synthetic/real, page and word counts, scan resolution and expected reference
matches. Import an authorized representative corpus through the normal UI.
The automated kit's 20 generated sources are only synthetic load fixtures.

## Hardware and executable trial (PowerShell, checkout root)

```powershell
New-Item -ItemType Directory -Path C:\Stage8LResults -Force
powershell -NoProfile -File tools/stage8l_hardware.ps1 -OutputFile C:\Stage8LResults\hardware.json
Get-FileHash 'C:\Stage8LCandidate\Arabic-Academic-STAGE8L-Candidate.exe' -Algorithm SHA256
powershell -NoProfile -File tools/standalone_low_resource.ps1 -Candidate 'C:\Stage8LCandidate\Arabic-Academic-STAGE8L-Candidate.exe' -DataDirectory 'C:\Stage8LTrialData' -Port 5058
```

In a browser open `http://127.0.0.1:5058`. Perform normal first-administrator
setup, recovery enrollment and login. Do not put credentials or recovery cards
into shared evidence. Record first-launch-to-browser-ready time and whether a
second browser window remains responsive during analysis. Confirm exactly one
background analysis worker in the candidate logs/process tree.

With the NORMAL scientific settings (record them; do not disable components to
pass), upload authorized 10/50/100-page PDFs, DOCX and scanned Arabic PDF. Record
per-request time, extraction success/quality, matched sources, report generation
and AI unavailable/disabled status. Repeat consecutive uploads at least ten times
and record memory after each. Missing AI assets must not block plagiarism-only
results. Keep experimental model scores out of all production reports.

Run Windows Performance Monitor during the executable trial: process tree RSS
and private bytes, total system commit/limit, available RAM, CPU, pages input/
output per second and paging-file occupancy. A Word COM server may be outside
the Python/executable child tree: observe it separately without killing an
existing user Word session. Preserve counter CSVs with timestamps. Localized
counter names may require manual selection. Memory page-ins can include mapped
files; they are not solely page-file reads attributable to this app.

Create a backup using the normal UI, validate it, shut down gracefully, then
restore only into a **second disposable trial installation/data directory**.
Stage 8M found that a full backup can omit uploaded report source files even when
its database validates. Check coverage before relying on a backup:
`python tools/audit_backup_report_coverage.py PATH_TO_BACKUP.zip`. A nonzero exit
means report sources are missing; a zero exit checks names only and is not proof
of integrity or successful restore. Do not rely on an incomplete archive.
Verify report IDs/content, corpus and SQLite persistence after restart. Record
restore outcome and integrity checks. Never test destructive restoration against
production storage. Verify shutdown releases owned workers and files, including
Word DOCX originals and operation temporary files. Preserve native RPC diagnostics
and every failed request; successful retries do not erase failures.

## Automated source-workflow supplement (not executable acceptance)

```powershell
powershell -NoProfile -File tools/standalone_low_resource.ps1 -Benchmark -Workflow plagiarism -OutputDirectory C:\Stage8LResults\plagiarism-run1
powershell -NoProfile -File tools/standalone_low_resource.ps1 -Benchmark -Workflow research -OutputDirectory C:\Stage8LResults\research-run1
```

Repeat with `run2`/`run3` fresh directories and fresh Python processes. For the
research mode include local tokenizer/model/hash manifests; do not invent missing
measurements. Preserve all individual runs, not only the fastest. The synthetic
test client uses isolated DB/storage and antivirus/authentication doubles, and
disables semantic inference in its request settings. It is a resource/lifecycle
supplement, not the normal packaged production path or academic accuracy test.

For a normal/default versus low-resource comparison run the existing runner in
a separate fresh PowerShell with `STAGE8J_DIRECT_TOKENIZER=1`, `STAGE8K_REPEATED=1`,
`STAGE8J_OUTPUT_DIR` pointing to a new results folder, and use
`python tools/stage8j_target_benchmark.py --corpus populated --workflow plagiarism`
(or `research`). Record all effective limits from JSON. Do not compare a warmed
process to a fresh process as though it were a controlled configuration trial.

Repeat Word/OCR regression probes when the offline Python environment is available:

```powershell
$env:RUN_STAGE8K_WORD='1'
python -m pytest -q -s tests/test_stage8k_real_word.py tests/test_stage8k_word_lifecycle.py
Remove-Item Env:RUN_STAGE8K_WORD
$env:STAGE8K_OCR_TIMINGS='1'
python -m pytest -q -s tests/test_job_management.py::test_cross_process_ocr_crash_recovery
```

## Decision record

Record CPU, Windows build, installed/free RAM, storage type, page-file policy,
candidate/source hashes, software versions, normal settings, authorization,
all startup/request times, per-request retained memory, sampled peaks, paging,
crashes/OOM, converter remnants, file locks, retries and browser responsiveness.
Define acceptable latency/responsiveness before the trial; do not choose cutoffs
after seeing results. Record any unrelated background workload.

Give **separate** PASS / PASS WITH LIMITATIONS / FAIL / NOT VERIFIED decisions
for plagiarism-only standalone, additional research inference and future LAN.
Any unexecuted mandatory acceptance step remains NOT VERIFIED. A functional
failure is FAIL for that condition. Unstable/accumulating resources, missing
dependencies, invalid integrity evidence or unacceptable responsiveness prevent
an unqualified PASS. LAN readiness requires a separate multi-client server trial.
Independent Arabic academic AI accuracy is still a blocker to production AI
activation, even if research inference fits the target hardware.
