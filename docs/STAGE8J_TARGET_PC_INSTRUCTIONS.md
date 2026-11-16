# Stage 8J target-PC measurement procedure

This is an isolated research benchmark, not a production AI installer. Run on
the actual Windows 4GB/i3 PC before deciding compatibility. Keep production AI
disabled. Synthetic results do not measure detection accuracy.

The generated `scratch/stage8j/Stage8J-benchmark-kit.zip` is a source overlay
containing the benchmark tools/tests, instructions and evidence. Extract it over
this existing checkout. It does not contain a Python environment, model weights,
OCR installation or the whole application; transfer those prerequisites below.

## Offline transfer

Transfer this checkout including tests and tools, a compatible installed Python
environment or offline wheelhouse for its exact Windows/Python architecture,
the existing local OCR executable and Arabic language assets, and these verified
research files (ignored scratch assets are NOT included by a normal git clone):

- `scratch/stage8f/nawaf/`: configuration, tokenizer, vocabulary, special token
  metadata, original safetensors, publisher card.
- `scratch/stage8f/hashes_nawaf.json`.
- `scratch/stage8h/nawaf_int8.jit` and `nawaf_int8.manifest.json`.

Use the existing package/source SHA-256 checks; do not regenerate manifests to
accept a mismatch. Expected INT8 artifact SHA-256:
`4c49debe9d7982b596539d131507e3a388db5dff570a66a9e35553dadbe57d6e`.
Expected source safetensors SHA-256:
`09b9c696070c49b0ee6364228d26f3d81aa5481a0bb1754f1710d541200f94a8`.
Model revision: `c6378eec16e00ff496765a08edeed27e0f030aab`.
Current source directory totals 543,345,751 bytes; INT8 artifact is 284,793,015
bytes. Budget at least 828,138,766 bytes for these alone, plus manifests, Python,
runtime dependencies, OCR, application, corpus, temporary conversions and reports.

The development environment used Python 3.13.2, Torch 2.9.1+cu128 (CPU inference),
Transformers 5.3.0. This large development Torch build is not a proven minimal
offline distribution. A CPU-only wheel substitution needs a separate measured
validation. Capture `python -m pip freeze` and `python -m pip check` on the
packaging machine; resolve its known NumPy/SciPy incompatibility in an isolated
environment before shipping. No complete dependency wheelhouse was produced in
this stage. Run the parity check before using the direct tokenizer optimization.

## Execution (PowerShell, repository root)

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:RUN_STAGE8J_PARITY='1'
python -m pytest -q tests/test_stage8j_tokenizer.py
Remove-Item Env:RUN_STAGE8J_PARITY
python tools/stage8j_target_benchmark.py --corpus empty
python tools/stage8j_target_benchmark.py --corpus populated
# Save the baseline scratch/stage8j JSON/logs before the following runs:
$env:STAGE8J_DIRECT_TOKENIZER='1'
python tools/stage8j_target_benchmark.py --corpus empty
python tools/stage8j_target_benchmark.py --corpus populated
```

Each command starts a fresh Python subprocess. Save each run under a distinct
directory before rerunning the same corpus profile: filenames otherwise overwrite.
The tests use a temporary database/storage tree and an antivirus test double;
they do not exercise production authentication or network-server behavior.
The populated profile imports 20 generated reference sources and checks every
import succeeds. It is a load fixture, not a realistic academic collection.
The synchronous extraction route can invoke local OCR even though the plagiarism
settings disable semantic inference. Missing DOCX/OCR prerequisites are recorded
as failed workload outcomes, not compatibility successes.

Collect at least three fresh-process runs of each profile and preserve the
individual observations. Do not average the first cold request into warm latency.
Record CPU model, Windows version, total RAM, page-file policy, available disk,
free RAM before testing, OCR versions and document characteristics.

## Additional required observations

The runner writes host commit/available physical RAM samples, test logs and exit
status to `scratch/stage8j`. The test writes request timings and process-tree
working-set/private-byte peaks. System counters include other applications.
Process-tree working sets can double-count shared pages. Private bytes are
commit, not physical RAM. Peaks are sampled and may miss transient allocations.

Use Windows Performance Monitor concurrently to record `Memory\Available MBytes`,
`Memory\Committed Bytes`, `Memory\Commit Limit`, `Memory\Pages Input/sec`,
`Memory\Pages Output/sec`, `Paging File(_Total)\% Usage`, processor utilization
and relevant process private bytes/working set (counter names may be localized).
Keep the page-file policy recorded and unchanged between comparisons.
Record crashes, OOM events and whether a separate browser remains responsive.
Then run the real packaged application with normal authentication/antivirus and
authorized representative documents. This test-client harness alone cannot
establish full deployment reliability, real DOCX quality, or LAN concurrency.

For standalone testing start with one worker and one active analysis. For LAN,
test a bounded queue on the same application architecture; do not multiply model
copies across workers without measuring aggregate server memory. These are
deployment recommendations, not newly implemented production limits.
