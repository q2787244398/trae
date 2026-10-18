# restart-all.ps1 - stop everything, wait, start again.
# Used by launcher.ps1 and by the "重启 Trae Relay" desktop shortcut.

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host '============================================================' -ForegroundColor DarkGray
Write-Host '  Restarting Trae2api-cn' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor DarkGray

& (Join-Path $Root 'stop-all.ps1')
Start-Sleep -Seconds 2
& (Join-Path $Root 'start-all.ps1')
