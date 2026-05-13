$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Invoke-Step "ruff format check" {
    & $python -m ruff format --check .
}

Invoke-Step "ruff lint" {
    & $python -m ruff check .
}

Invoke-Step "pytest with coverage" {
    & $python -m pytest --cov=wagom_player --cov-report=term-missing --cov-report=xml
}

Invoke-Step "git diff whitespace check" {
    git diff --check
}

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
