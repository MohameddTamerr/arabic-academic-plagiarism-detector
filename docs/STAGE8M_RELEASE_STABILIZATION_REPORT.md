# Stage 8M — release stabilization and backup repair

## Current decision

| Area | Verdict | Reason |
|---|---|---|
| Plagiarism-only software | PASS WITH LIMITATIONS | Regression passed except the preserved historical manifest mismatch; representative institutional data and target hardware remain limited. |
| Backup and restore | PASS WITH LIMITATIONS | Isolated source restoration and failure tests passed; settings are not automatically restored and legacy/concurrent edge cases remain. |
| Windows candidate | PASS WITH LIMITATIONS | The separate Stage 8M build passed isolated upload, restore and restart checks on the development laptop; packaged graceful shutdown and target hardware remain unverified. |
| Actual 4GB Windows compatibility | NOT VERIFIED | The available development laptop has 34,011,582,464 bytes RAM; the actual 4GB PC was not accessible. |
| Production AI detection | NOT VERIFIED | Independent Arabic academic accuracy and false-positive evaluation are absent; production AI remains fail-closed. |
| Offline LAN server | NOT VERIFIED | No representative multi-client server acceptance test. |

These verdicts do not treat development-laptop speed or synthetic data as target
hardware compatibility or authorship accuracy evidence.

## Original backup defect

The Stage 8L reference candidate saved three generated PDF/DOCX/scanned report
records and the corresponding files under `Storage/temp_uploads`. Its full backup
contained all three database records but no original documents: backup enumeration
only included rows registered in `research_files`. The code created a reference-file
staging directory but did not populate it. SQLite `integrity_check` and ZIP CRC
checks passed, so they did not identify missing originals. Isolated extraction of
the backed-up DB still found three reports, but was not a complete file restore.
The read-only coverage diagnostic identifies the three omitted report IDs. It is a
coverage aid, not a replacement for cryptographic backup validation.

## Repair implemented in the development source

- Use SQLite's online backup API and convert the destination snapshot to a
  self-contained rollback-journal database; reject unverified non-empty WAL files.
- Enumerate database-referenced report, reference, thesis-part and research paths,
  including paths in multi-file report JSON. Snapshot only referenced files inside
  configured local application storage, not staging, preview, OCR or model caches.
  Missing, external, changed or hash-mismatched files cause backup failure.
- Stream file data and hashes in 1 MiB blocks. Deduplicate archived content by
  SHA-256, verify source and staged bytes before and after copy, preserve associated
  content-addressed-store metadata, and verify it during restore. New report saves
  record the source SHA-256; older reports without an original hash can only be
  checked against the bytes present at backup time.
- Record reference identities using path fingerprints rather than publishing
  absolute server paths in the manifest. Validate the manifest against the
  database snapshot, sizes and hashes, and check configuration/metadata hashes.
  Historical archives without source coverage are rejected as incomplete; a legacy
  archive with an unambiguous integrity-listed source for every reference remains
  supported. Original historical archives are never rewritten.
- Build under a unique `.partial` name; validate before publication, publish
  without replacing an existing archive, and reject partial/creating/failed
  backups as complete. Snapshot, inspection and restore directories use unique
  names; cleanup is restricted to operation-owned directories under trusted roots.
- Reject archive traversal, absolute/drive paths, unsafe Windows aliases, duplicate
  case-insensitive entries, symlinks, unlisted files and unverified WAL contents
  before extracting. Restore writes originals to unique new storage locations,
  verifies them and rebases database file paths before replacing the live DB.
  Existing report JSON, canonical payloads and historical hashes are not rewritten;
  a hash-verified mapping resolves original paths inside immutable multi-file JSON.
- A safety-backup ID collision with a copied archive was also repaired. On failure
  after database replacement, restore rolls back the database; new restore paths
  do not overwrite pre-existing uploads. A failure before DB replacement avoids an
  unnecessary DB rollback. Existing audit events still record restore outcomes.

The stored academic settings file is included and hashed in new backups, but the
current restore implementation does **not** apply that configuration file. A
failed restore can also leave newly created content-addressed objects as harmless
orphans; existing CAS objects are never overwritten. Full atomicity against an
independent process modifying legacy unhashed files between the SQLite snapshot
and initial file read is not established. These are limitations, not proven
complete system recovery. Non-filesystem storage and real institutional datasets
have not been validated.

## Restoration, OCR, Word and shutdown evidence

An isolated Flask test created PDF and DOCX reports, backed them up, deleted only
the generated fixture originals, and restored into a separate test database and
storage directory. Both report IDs and document hashes survived; PDF/DOCX preview
and highlight endpoints responded, multi-file JSON resolved without modifying the
stored JSON, a CAS content file and metadata were restored, and SQLite integrity
passed. A subsequent backup of restored data and a database rebind succeeded.
The synthetic PDFs contain no independently verified matching passage; a successful
highlight endpoint is not proof of highlight coordinate accuracy. Failure tests
cover missing or changed sources, disk-full injection, tampered or missing blobs,
corrupt DB/config/metadata, interrupted files, unsafe ZIP aliases, non-empty WAL,
and rollback before and after database replacement. Catalog validation rejects
creating/failed entries.

The Stage 8L candidate, before repair, was separately checked with generated PDF,
DOCX and scanned uploads: reports reopened, logout blocked access (401), and a
report reopened after restart. Those old-candidate results do not test this repair.
Repeated real Word/OCR tests in Stage 8M: **18 passed**, 14 warnings, 18.92 seconds.
Word native RPC diagnostics still appeared; the tests observed file release and
process exit, but their underlying cause and hung-Word timeout remain unresolved.
OCR fixture startup/recovery passed repeated synthetic trials, not an accuracy test.

The separately built Stage 8M executable was also tested through its authenticated
local HTTP interface using isolated application directories and three synthetic
uploads: PDF, DOCX and scanned PDF. All three reports had AI status unavailable.
The backup contained all three source hashes, backup validation and isolated
restore returned HTTP 200, the restored SQLite database passed `integrity_check`,
and all three original documents matched their pre-backup SHA-256. Report and
preview-info endpoints returned 200 after restore, and all reports returned 200
after a second start. The test process tree was forcibly stopped; this does not
prove graceful packaged shutdown. See `scratch/stage8m/candidate_restore_probe.json`.
The fixture has no known matching passage, so it does not validate highlight
coordinates or plagiarism accuracy.

On the 34 GB development laptop, the candidate trial sampled a process-tree peak
of 1,029,971,968 bytes RSS and 1,053,507,584 bytes private memory. Three startup
samples were 20.71, 16.12 and 28.30 seconds. These are synthetic, sampled values,
may omit separately hosted Word processes, and do not establish behavior on a
4 GB PC or with large institutional files.

A backend controller test started/stopped a real loopback Waitress server twice,
verified SQLite integrity and PID/lock cleanup, and used a test-owned dummy worker.
The controller terminates that worker; this is not a validated graceful drain of
an active real analysis worker. Full GUI/tray and packaged-executable graceful
shutdown remain NOT VERIFIED. No browser safety restriction was bypassed.

## Research dependency isolation

Stage 8L had nine setup errors caused by incompatible Transformers/Hugging Face
imports. In the current shared interpreter, the same nine tests reproduced as
`BertTokenizer` constructor errors with Transformers 4.57.6. A separate
`--system-site-packages` research overlay using Python 3.13.2, Transformers 5.3.0,
Hugging Face Hub 1.3.0, Tokenizers 0.22.2 and typer-slim 0.24.0 passed the affected
group: **10 passed**, 11 warnings, 99.53 seconds. An earlier overlay with Hub 1.33.0
also passed 10, but introduced additional dependency conflicts.

The tested inherited packages include Torch 2.8.0, NumPy 2.4.6, SciPy 1.15.2,
scikit-learn 1.6.1 and ONNX Runtime 1.24.4. This is not a hermetic environment;
`pip check` still reports inherited FastEmbed/Pillow, OpenCV/NumPy, WhisperX/Hub
and lightecc/pytest conflicts. Production packages were not upgraded or downgraded.
The tested overlay can be recreated from locally stored wheels, provided the same
base interpreter and dependencies are available:

```powershell
python -m venv --system-site-packages .venv-stage8m13
.venv-stage8m13/Scripts/python.exe -m pip install --no-index --find-links scratch/stage8m/wheels --no-deps -r requirements-stage8m-research.txt
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
.venv-stage8m13/Scripts/python.exe -m pytest -q tests/test_pretrained_research.py tests/test_sequence_research.py
```

The four wheels are not a complete offline wheelhouse or packaged Python runtime.
Torch and the other inherited packages are additional prerequisites. Research
models remain local-only and are not bundled into the production executable.
The candidate archive inventory contains the quantized multilingual E5 semantic
retrieval model (118,308,811 uncompressed bytes) and a `safetensors` runtime
library, but no Farras/AraBERT or research-detector weight file was found in the
archive inventory. The build explicitly excludes Torch and TensorFlow. This is
an inventory check, not a proof that every optional library was removed.

## Regression evidence so far

- Reproduced research baseline: **1 passed, 9 errors**, 9 warnings, 27.67 seconds.
- Isolated affected research group: **10 passed**, 11 warnings, 99.53 seconds.
- Plagiarism/source-retrieval/alignment/citation/review/report group: **79 passed**,
  22 warnings, 5.15 seconds, before this backup repair.
- Post-repair backup/recovery/review/AI-safety group: **84 passed**, 526 warnings,
  26.95 seconds. A focused rollback and lifecycle group passed **15 tests**.
- Previous full regression, before the repair: **915 passed, 2 failed, 5 skipped**,
  3,293 warnings, 508.08 seconds. The failures were the historical manifest
  mismatch and an executable-launcher test copying a venv redirector without its
  configuration. The latter was corrected to use the base interpreter and passed
  individually. Historical integrity evidence and assertions remain untouched.
- First post-repair full regression: **921 passed, 11 failed, 5 skipped**,
  3,491 warnings, 384.47 seconds. Ten backup failures were caused by earlier
  tests leaving temporary report and fictional thesis paths in the session-wide
  test database; the remaining failure was the historical manifest mismatch.
- Final post-repair full regression after fixing the test fixtures: **931 passed,
  1 failed, 5 skipped**, 3,543 warnings, 329.79 seconds, with no test errors.
  The one failure remains `test_release_manifest_integrity_and_hashes`: the
  historical manifest expects a different `config.py` hash. The original manifest
  and test assertion were preserved. The Word tests emitted native Windows RPC
  diagnostics during the run but pytest continued and completed.

The executable candidate test is separate from the source regression; older
candidate results do not demonstrate the repaired executable's behavior.

## Modified files

`app/services/backup_service.py`, `app/services/backup_persistent_files.py`,
`app/repositories/report_repo.py`, `app/routes/pdf_routes.py`,
`tests/test_stage8m_backup_sources.py`, `tests/test_stage8m_shutdown.py`,
`tests/test_exe_launchers.py`, `tests/test_batch.py`,
`tests/test_final_admin_rbac_gate.py`, `tools/audit_backup_report_coverage.py`,
`requirements-stage8m-research.txt`, `tools/stage8l_freeze_candidate.py`, and
`docs/STAGE8L_OPERATOR_INSTRUCTIONS.md`, `docs/STAGE8M_TARGET_PC_INSTRUCTIONS.md`,
plus this report and test evidence. The two existing tests now clean up their
own report or use actual isolated thesis fixture files; the backup checks were
not relaxed.

The separately named candidate is
`scratch/stage8m/candidate/Arabic-Academic-STAGE8M-Candidate.exe`, 494,082,844
bytes, SHA-256 `ba8b9a601cb3157a345388318615ce0c7c6bc7118a49f96cb6ee6e3740fe4b09`.
It was built from `scratch/stage8m/frozen_source_final`; its source manifest
SHA-256 is `6e85b865db9c4e5b681095f3efe91d7dd27a4f2de3e3fe131f765b48851f9543`.
All 5,158 listed snapshot files matched their hashes after the build. The source
snapshot predates the two test-fixture-only cleanup changes described above;
the executable's application code is unchanged by those changes. The build took
578.77 seconds on the development laptop.

Stage 8L remains the reference candidate (SHA-256
`4c0309fba8f36915f685a715c6c7c3757bf6ab9e6325251f228d6388bed04a27`) and was not
overwritten. Actual 4GB PC testing, a complete
offline dependency package, representative academic data, production AI accuracy,
and LAN concurrency validation remain external blockers.
