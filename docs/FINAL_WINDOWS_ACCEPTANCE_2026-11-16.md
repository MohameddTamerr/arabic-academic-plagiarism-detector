# Windows release acceptance | 16 November 2026

## Release notes

- Integrated the reviewed frontend patch from `8ebb1eb` and the accompanying documentation from `9a999fc`. The branch also contained an earlier backend snapshot. Integration applied the four reviewed files directly to the current checkout.
- The primary Analyze action uses the selected OCR mode and prevents duplicate submission while its request is active. The report view resets its tabs when a different report opens and falls back to evidence when a PDF preview is unavailable.
- Report submission and replacement-PDF uploads enforce department scope and review state. Submission records the authenticated username. Completed report results returned by task, batch-item and thesis status routes enforce report read scope and the fail-closed AI response.
- Live task status, batch status and retry, and research and batch listings enforce the authenticated owner’s department scope. New scan records carry the authenticated username. Administrators can inspect older batch and task records whose owners cannot be resolved to accounts.
- Production AI remains unavailable with `validation_status: no_validated_model`. Research fixtures cover abstention and error isolation. No authorship accuracy is reported.
- Added a current source-integrity manifest. A candidate build compares it with frozen source inputs and writes a separate executable manifest and checksum. The historical manifest and historical releases are retained.
- `--show-console` opens the launcher’s administration panel for the supported graceful stop workflow. The regular startup still uses the system tray.

## Changed files

- Frontend and regression coverage in `templates/index.html`, `tests/test_frontend_production_ux.py` and `tests/test_ui_shell.py`.
- Authorization and workflow in `app/security/authorization.py`, `app/routes/{scan,batch,report}_routes.py`, `app/repositories/{batch,report}_repo.py` and `tests/test_final_admin_rbac_gate.py`.
- Packaging and launcher in `app/single_exe/entrypoint.py`, `tools/{package_windows_candidate,stage8l_freeze_candidate}.py`, `release_source_manifest.json` and `tests/test_release_candidate.py`.
- Test isolation in `tests/test_stage8m_backup_sources.py`. Documentation in this report, `docs/FRONTEND_RELEASE_CHANGESET.md` and `docs/WINDOWS_RELEASE_USER_GUIDE.md`.

## Report and review API

| Endpoint | Acceptance contract |
| --- | --- |
| `POST /api/scan`, `POST /api/batch/independent`, `POST /api/batch/thesis` | The existing upload flow accepts `ocr_mode` values `fast` and `accurate`. The Analyze button submits the selected mode. The resulting report exposes independent engine statuses. |
| `GET /api/tasks/<id>`, `GET /api/batch/<id>/item/<research_id>/report`, `GET /api/thesis/<id>/status`, `GET /api/reports/<id>` and `/summary` | Completed report data follows report access rules. `plagiarism_analysis` keeps its existing status and the top-level similarity fields. `ai_analysis` reports `status: unavailable`, `validation_status: no_validated_model`, `model: null`, `paragraphs: []` and four null percentage fields. The reason reflects whether the setting is disabled, a validated model is unavailable, or analysis failed. |
| `GET /api/reports/<id>/evidence`, `GET /api/pdf/report/<id>/info`, `GET /api/pdf/report/<id>/highlights?page=1` | Evidence remains scoped to report readers. Highlights refer to the PDF page coordinate system and merged-thesis documents retain their file indices. |
| `POST /api/reports/<id>/submit_to_admin` and `/upload_latest_pdf` | Cross-department access is refused. Submission records the authenticated account. State conflicts return HTTP 409. Replacement PDFs require preliminary acceptance and a current draft. |
| `GET /api/batches`, `GET /api/researches`, `GET /api/batch/<id>` and `POST /api/batch/<id>/item/<research_id>/retry` | Inaccessible rows are filtered before pagination. Direct cross-department batch reads and retries return HTTP 403. |

## Installation

Follow the [Windows installation and operation guide](WINDOWS_RELEASE_USER_GUIDE.md). The installation check uses a fresh data directory, localhost and one worker. Use an unused port and a locally installed, operational antivirus. Keep the test account and its recovery card within the isolated trial.

Distribute the executable together with `RELEASE_MANIFEST.json` and `SHA256SUMS.txt`. This candidate is unsigned. The SHA-256 verification checks file integrity. Keep an independent, verified backup of an existing installation and use a separate data directory for initial acceptance.

From the repository root on the Windows AMD64 Python 3.13 build workstation, use a fresh destination.

```powershell
$env:PYTHONUTF8 = '1'
$out = Join-Path $PWD 'scratch\windows-release-next'
python -m tools.package_windows_candidate $out
if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed' }
$exe = Join-Path $out 'Arabic-Plagiarism-System-Windows8GB-RC.exe'
python -m tools.verify_release_provenance $exe `
  (Join-Path $out 'RELEASE_MANIFEST.json') (Join-Path $out 'SHA256SUMS.txt')
if ($LASTEXITCODE -ne 0) { throw 'Candidate verification failed' }
```

## Measurement scope

The development host is Windows 11 Home build 26300 with an Intel Core i5-12500H and 31.68 GiB physical RAM. The executable probe uses fresh and restored SQLite roots, one worker, a Windows-only `PATH`, loopback HTTP and offline model settings. The browser test denies requests to non-loopback addresses. Application process-tree measurements sample working set and private bytes. External service processes such as an independently hosted Word instance may be outside the tree.

Uploads are generated acceptance fixtures with known source passage overlap. They exercise matching and highlighting without making academic accuracy claims. A preflight PDF with an unreadable native text layer produced OCR matches and no reliable coordinates. The native highlight assertion uses a PDF with an embedded Arabic-capable font and a readable text layer.

## Build and source tests

| Check | Result |
| --- | --- |
| `python -m pytest -q -rs --tb=short` | 961 passed, 0 failed, 5 skipped and 3,565 warnings in 520.22 s. |
| Opt-in local research model and tokenizer tests | 2 passed in 81.92 s using local assets and fixture data. They exercised runtime and tokenizer parity. |
| Opt-in Microsoft Word lifecycle | First run had 2 passes and 1 failure in 29.17 s. A Word process stayed alive beyond the five-second grace period. Isolated repeat had 3 passes in 16.19 s. |
| Windows build and provenance | `windows-final-acceptance-rc2`, 494,153,343 bytes. SHA-256 `93a836d4eab7bbd838f74dd2f1f672750529d43a79a6a39fef1c65cd700cbd89`. All 59 critical pins matched the frozen inputs. The executable, release manifest and checksum file verified together. |
| Executable contents | The reviewed HTML matches the embedded template. The archive contains the E5 INT8 similarity model and Arabic and English OCR models in both speed profiles. Research authorship weights, Torch, TensorFlow, Transformers, CUDA and TensorRT provider binaries are absent. |

The source suite exercised AI abstention, malformed inputs, model failures and error isolation. The real-model opt-in cases provide no estimates of authorship accuracy. The first scoped suite run caught a version assertion that still named the previous candidate. The correction was in the test only, after the executable source freeze, and retained exact checks against all pinned input files.

## Packaged executable acceptance

| Check | Observed result |
| --- | --- |
| Fresh startup | Waitress ready after 53.50 s in a new data directory. The listener bound to `127.0.0.1`. |
| One-page native Arabic PDF | 5.36 s from upload to completed report, 0.41 s on repeat. The seeded reference matched and the report returned 2 evidence items and 4 rectangles within page bounds. |
| DOCX and raster PDF | DOCX completed in 8.04 s and returned a one-page preview. Raster PDF completed in 1.96 s and returned 53 extracted words and a similarity result. |
| Multi-document thesis | Two ordered PDF and DOCX files completed in 7.52 s. Results retained both file indices and both previews opened. |
| Browser workflow | One primary Analyze action, selected fast OCR retained, evidence and sources tabs populated, loaded PDF page and highlight overlay, visible AI unavailable status, and zero console errors on the recorded flow. |
| Permissions and review | Anonymous admin endpoint returned 401. Employee admin access, cross-department task and report reads, batch reads and retries, and cross-department review mutations returned 403. Unauthorized entries were absent from listings. The reviewer granted preliminary acceptance, final acceptance was restricted, an administrator finalized the report, and the certificate returned 200. Resubmission and PDF replacement after final approval returned 409. |
| AI fail-closed | Reports returned `unavailable` and `no_validated_model` with no paragraph predictions, model, or percentages, even with the experimental setting enabled. Similarity and evidence remained available. |
| Backup and restore | Backup and archive validation took 1.69 s. It contained seven distinct persistent file digests. Restore and verification took 10.74 s, including byte-for-byte verification of four report source files and two thesis source files, both thesis previews, and SQLite integrity `ok`. |
| Graceful shutdown and restart | All three native shutdowns exited with code 0, released the listener and instance lock, and exited their frozen child processes. The active scan completed and persisted before exit. The active shutdown took 9.89 s in the application log. Idle shutdowns took 0.63 s and 0.72 s. Five verified reports reopened after restart. |
| Academic PDF excerpt | 24 pages, 7,909 extracted words. End-to-end completion took 27.27 s on the first scan after restart and 21.90 s on repeat. This workload used a small local reference corpus. No scan errors were recorded. |
| Offline and RAM | Offline settings, unreachable outbound HTTP proxies, and a loopback-only browser routing rule were active. Periodic network samples observed zero non-loopback peers. Across 4,254 process-tree memory samples, maximum working set was 997.04 MiB and private memory was 1,036.87 MiB. A second clean data root started in 35.92 s and the restored root restarted in 35.85 s. |

The full [source test log](../scratch/windows-release-scoped-tests-final.log), [packaged probe results](../scratch/windows-release-scoped-validation-20261116/results.json), [browser operations](../scratch/windows-release-scoped-validation-20261116/browser/operations.log), and [release manifest](../scratch/windows-release-scoped-20261116/RELEASE_MANIFEST.json) record the measurements. Scan timings include the HTTP upload and polling, excluding subsequent preview retrieval. The shutdown timings use application log events. These trials used isolated data directories and left existing installations and their data in place.

## Remaining limitations and deployment decision

**NO-GO for production deployment.** The executable is a release candidate for isolated plagiarism workflow trials. The target check still requires a clean, network-disconnected Windows host with 8 GB of RAM and a realistic reference corpus. The development host’s memory observations establish the measured workload’s footprint on that host.

- Authorship analysis remains `no_validated_model`. Production use requires an authorized Arabic academic evaluation set and independent validation. The local E5 graph serves similarity matching. The [evaluation and paragraph offset instructions](WINDOWS_8GB_RELEASE.md) apply to the separate research workflow.
- DOCX analysis and PDF preview depend on different components. Word preview worked in the packaged run. Word COM could intermittently fail to expose the process handle, and one source lifecycle trial exceeded its five-second grace period. Verify converter lifecycle on the deployment Office build. A local antivirus must be operational for uploads.
- Raster OCR can recover matching text. Only pages with trustworthy anchors can display precise highlight rectangles. Test target document formats and corpus size before deployment.
- The Windows artifact has no Authenticode signature. Compare its SHA-256 against the supplied checksum through a trusted distribution channel.
- The earlier [25-page tokenization comparison](WINDOWS_8GB_RELEASE.md) measured preprocessing speed and span compatibility. The packaged system uses the existing preprocessing.
