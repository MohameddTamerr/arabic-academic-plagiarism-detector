# Stage 8M target-PC validation

The Stage 8M candidate is experimental until the separate executable smoke test
and an actual 4 GB Windows test are recorded in the Stage 8M report. Do not use
it as the only copy of institutional data. Keep the Stage 8L candidate and all
existing backups unchanged.

On an isolated Windows PC, first make a new, dedicated test directory and run the
candidate there using test documents only. Keep the PC offline. Record the Windows
version, processor, installed and available RAM, free disk space, antivirus status,
whether Microsoft Word and the configured OCR tools are present, and executable
SHA-256. Record cold startup, document size and analysis time, peak process-tree
memory, and whether the application and its owned child processes close cleanly.
Do not infer 4 GB compatibility from the development laptop's measurements.

In a separate test data directory, create PDF and DOCX reports, make and validate a
backup, restore that archive into another isolated test installation, and check
the report IDs, original files, previews, hashes, and reopening after restart.
Use the application's normal authentication and restore controls. Never test
restore over real institutional data. A backup made by an older candidate may
omit source files; audit it before relying on it:

```powershell
python tools/audit_backup_report_coverage.py <backup.zip>
```

This diagnostic checks coverage; it is not a substitute for application integrity
validation. New backups include settings, but the present restore does not apply
them; configure the destination separately and verify settings before any use.
Research-only AI detection remains disabled. OCR requires locally installed and
configured OCR components; Word conversion depends on its locally available
runtime. A complete offline wheelhouse and target-PC acceptance are not yet
available. See `STAGE8M_RELEASE_STABILIZATION_REPORT.md` for the actual results
and deployment limitations.
