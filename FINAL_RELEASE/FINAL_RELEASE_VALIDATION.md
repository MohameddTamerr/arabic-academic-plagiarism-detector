# RC3 Release Validation

Generated: 2026-10-09T12:38:34+03:00

## Canonical artifact

- File: `windows-modern/Arabic-Plagiarism-System-RC3.exe`
- Size: `487828437` bytes
- SHA-256: `905085318d59a5014fa327a5203a71b915bad65734bf942bf36999bf8fb87b72`
- Source commit: `7c2971492d5670086e93d3b90f7c2f0a8f36783a`
- Source branch: `main`
- Source state: working tree dirty; exact changed-file list is recorded in `RELEASE_BLOCKER_REPAIR_REPORT.md`.
- Build: Windows 11 Home AMD64, Python 3.13.2, PyInstaller 6.19.0.

## Provenance rule

`RELEASE_MANIFEST.json`, `SHA256SUMS.txt`, and the artifact above must match exactly. Run:

```powershell
python tools/verify_release_provenance.py FINAL_RELEASE/windows-modern/Arabic-Plagiarism-System-RC3.exe FINAL_RELEASE/RELEASE_MANIFEST.json FINAL_RELEASE/SHA256SUMS.txt
```

The build log records one optional `tbb12.dll` warning from NumPy/Numba discovery. It is not treated as a successful runtime validation; RC3 smoke-test and regression results must be read from the blocker-repair report.
