# dump-token.ps1 - read the local Trae client credentials for manual account add.

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$App  = Join-Path $Root 'Trae2api-cn\Trae2api-cn-main'
. (Join-Path $Root 'relay-env.ps1')
$Py = $RelayPython

Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '  Local Trae credentials (sensitive)' -ForegroundColor Yellow
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray

if (-not $Py) { Write-Host 'no Python interpreter found (relay-env.ps1)' -ForegroundColor Red; exit 1 }

Push-Location $App
try {
    & $Py (Join-Path $Root 'dump_token.py')
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Press any key to close ...' -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
