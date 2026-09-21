# Conservative recovery: stopped before repair

The request's section 60 requires stopping when detector runtime settings are ambiguous. That condition was found. No application source, settings, credentials, database records, storage, or binary was changed. This is an initial inspection report, not completed repair or runtime certification.

## A. Original HEAD / recovery point

- Branch: `main`.
- HEAD: `fbfd653c16b67ed7a014d74cdc886195e13ec463`.
- Initial `git status --short`, `git diff --stat`, and `git diff`: empty.
- Recovery branch: `recovery/2026-09-16-before-repair`, verified at the original HEAD.
- The recovery branch preserves tracked source only; it is not a user-data backup.

## B. Files changed

Only this report was added. No source repairs or database migrations were performed.

## C. Findings and stop condition

1. `config.py:162` defines shingle size 4, Jaccard 0.33, TF-IDF 0.35, semantic threshold 0.70, semantic disabled, candidate limit 50, dual-channel retrieval, refined citations, and span-level common-text filtering.
2. Roaming saved settings use shingle size 5, Jaccard 0.45, TF-IDF/cosine 0.45, semantic disabled, LIGHT profile, and maximum allowed source pages 6. The default source-page limit is 5.
3. `settings_service.get_current_settings()` overlays saved settings onto defaults. `scan_service` passes the resulting settings into `report_builder`.
4. `report_builder.py:103` builds reference shingles using `config.DEFAULT_SETTINGS['shingle_size']`; line 399 builds query shingles using the scan settings. The Roaming path therefore mixes four-word reference shingles with five-word query shingles. This is a concrete incompatible configuration path, established by inspection; its impact was not measured by an executed scan.
5. `config.py:151` assigns the settings path under Config, then line 180 overrides it under APPDATA_DIR. Neither packaged candidate settings file exists. Source and packaged deployments also select different persistent databases.
6. UI report snapshot fallback values use 5-word shingles and 40% thresholds, differing from defaults. Some fields are replaced when a snapshot is present; no browser behavior was tested.
7. `upload_validation_service` proceeds when no antivirus engine is found, after timeout, and after scanner exceptions. It rejects specific threat exit codes but does not require a successful clean exit for every other result. Institutional fail-closed security is therefore not implemented across those inspected paths. No malware or uploads were used.
8. The user-management browser code requests `/api/admin/users`; the route exists, requires `users.view`, and returns a legacy `users` response key. The reported connection failure has not been reproduced or attributed to a confirmed root cause.

No detector value was selected or normalized. Resolve whether to preserve each deployment's current settings and explicitly authorize correcting the reference/query shingle inconsistency before source repair resumes.

## Database baseline

All three databases were opened directly with SQLite `mode=ro`, without importing the application or invoking initialization/migrations. Each returned `integrity_check = ok`. No private record contents or credentials were printed.

| Database | Users | Canonical system_admin | Research | Reports | Theses | Reference documents | Audit | Bootstrap |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `C:/Users/user/Downloads/Baba/Database/papers.db` | 0 | 0 | 0 | 0 | table absent | 0 | 0 | no state row |
| `C:/Users/user/AppData/Roaming/ArabicPlagiarismDetector/papers.db` | 67 | 18 | 2875 | 337 | 1 | 85 | 2967 | completed = 1 |
| `C:/Users/user/AppData/Local/ArabicAcademicPlagiarismSystem/Data/Database/papers.db` | 1 | 1 | 8 | 4 | 0 | 4 | 937 | completed = 1 |

Reference counts refer to the `documents` table, including all governance statuses. Legacy `admin` roles are preserved separately and not counted as canonical `system_admin`. The packaged database has one recovery credential record. No data mutation was issued. A before/after repair comparison is not applicable because repair stopped; concurrent application changes have not been ruled out.

## D–V. Required gate report

| Item | Result / evidence level |
|---|---|
| D. SYSADMIN preservation | Read-only role and closed-bootstrap baseline confirmed; restart/login invariant NOT VERIFIED |
| E. Employee RBAC | NOT VERIFIED |
| F. Navigation | NOT VERIFIED |
| G. User Management | NOT VERIFIED; runtime error not reproduced |
| H. Multi-file thesis | NOT VERIFIED; existing repositories/services/routes/tests remain intact |
| I. Combined report | NOT VERIFIED |
| J. Precise highlight | NOT VERIFIED |
| K. Internal PDF viewer | NOT VERIFIED |
| L. Antivirus fail-closed | FAIL by inspected error/unavailable paths; integration test not executed |
| M. Reference corpus | NOT VERIFIED |
| N. Final accept to corpus | NOT VERIFIED |
| O. Detector settings changed? | NO |
| P. Database data loss | No deletion or mutation issued; post-repair comparison not applicable |
| Q. Full test run 1 | NOT RUN; collected/passed/failed/skipped/duration unavailable |
| R. Full test run 2 | NOT RUN; collected/passed/failed/skipped/duration unavailable |
| S. Packaged EXE test | NOT RUN; no rebuild performed |
| T. Two-device test | NOT YET MEASURED |
| U. Remaining limitations | Audit incomplete; all remaining repair gates pending detector stop-condition resolution |
| V. Final EXE path + SHA-256 | No final EXE produced or certified |

Gate 0 has a clean tracked-source recovery point and read-only data baseline. No higher gate is claimed as passed. The existing binary is not evidence of repaired source.
