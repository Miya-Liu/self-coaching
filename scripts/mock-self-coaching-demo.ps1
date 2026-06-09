# Self-coaching loop demo — Windows PowerShell wrapper (no bash required).
# Usage: .\scripts\mock-self-coaching-demo.ps1
#        .\scripts\mock-self-coaching-demo.ps1 -WithHttp
param(
    [switch]$WithHttp
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) {
    $Py = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}
if (-not $Py) {
    Write-Error "Python not found on PATH. Install Python 3.11+ and retry."
}

$Args = @("$Root\scripts\mock_self_coaching_demo.py")
if ($WithHttp) { $Args += "--with-http" }

& $Py @Args
exit $LASTEXITCODE
