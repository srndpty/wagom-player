param(
    [string] $DiffRange = "",
    [switch] $Fix,
    [switch] $Check
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# 既定の挙動: ローカル実行では自動整形(-Fix)、CI ではチェックのみ(ゲート)。
# 明示的に -Fix / -Check を渡せば上書きできる。
if (-not $Fix -and -not $Check) {
    $inCi = ($env:CI -eq "true") -or ($env:GITHUB_ACTIONS -eq "true")
    if ($inCi) { $Check = $true } else { $Fix = $true }
}

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

if ($Fix) {
    Invoke-Step "ruff format" {
        & $python -m ruff format .
    }

    Invoke-Step "ruff lint fix" {
        & $python -m ruff check . --fix
    }
} else {
    Invoke-Step "ruff format check" {
        & $python -m ruff format --check .
    }

    Invoke-Step "ruff lint" {
        & $python -m ruff check .
    }
}

Invoke-Step "pytest with coverage" {
    & $python -m pytest --cov=wagom_player --cov-report=term-missing --cov-report=xml
}

Invoke-Step "git diff whitespace check" {
    if ($DiffRange) {
        git diff --check $DiffRange
    } else {
        git diff --check
    }
}

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
