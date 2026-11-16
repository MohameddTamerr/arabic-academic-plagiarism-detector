param([switch]$Benchmark,[ValidateSet('research','plagiarism')][string]$Workflow='research',
    [string]$OutputDirectory='scratch/stage8k',[string]$Candidate,[string]$DataDirectory,[int]$Port=5058,[switch]$Headless)
$ErrorActionPreference = 'Stop'
# Process-local settings: no persistent machine settings or AI enablement.
$env:MAX_CONCURRENT_SCANS = '1'
$env:SCAN_EXECUTOR_WORKERS = '1'
$env:SINGLE_EXE_WORKERS = '1'
$env:MAX_CONCURRENT_OCR_JOBS = '1'
$env:PDF_OCR_WORKERS = '1'
$env:MAX_CONCURRENT_INDEX_BUILDS = '1'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ($Benchmark) {
        $env:STAGE8J_OUTPUT_DIR=$OutputDirectory
        $env:STAGE8J_DIRECT_TOKENIZER='1'
        $env:STAGE8K_REPEATED='1'
        python tools/stage8j_target_benchmark.py --corpus populated --workflow $Workflow
    } elseif ($Candidate) {
        if (-not $DataDirectory) { throw 'A separate candidate DataDirectory is required' }
        $env:ARABIC_APP_DATA_DIR=[IO.Path]::GetFullPath($DataDirectory)
        $env:HOST='127.0.0.1'
        if ($Headless) { & $Candidate --headless "--port=$Port" }
        else { & $Candidate "--port=$Port" }
    } else {
        python server.py
    }
    $result=$LASTEXITCODE
} finally { Pop-Location }
exit $result
