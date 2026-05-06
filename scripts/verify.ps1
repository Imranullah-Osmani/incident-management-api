Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments
    )

    Write-Host $Label
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

$Python = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $Python = ".\.venv\Scripts\python.exe"
}

Invoke-CheckedCommand "Checking Docker Compose config..." "docker" @("compose", "config", "--quiet")
Invoke-CheckedCommand "Compiling application modules..." $Python @("-m", "compileall", "app", "recreated_sample", "tests")
Invoke-CheckedCommand "Running incident API tests..." $Python @("-m", "unittest", "discover", "-s", "tests")
Invoke-CheckedCommand "Running recreated case-study sample..." $Python @("recreated_sample/test_notification_pipeline.py")

Write-Host "Incident API verification completed successfully."
