# stop-all.ps1 - stop the relay, the Cloudflare tunnel and the auth helper.
# Usage: double-click stop-all.bat, or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\stop-all.ps1 [-ListOnly]

param([switch]$ListOnly)

$ErrorActionPreference = 'Continue'

function Get-PortOwners([int]$Port) {
    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { return @() }
}

$relayPids  = Get-PortOwners 8000
$helperPids = Get-PortOwners 8765
$cfProcs    = @(Get-Process cloudflared -ErrorAction SilentlyContinue)
$pyProcs    = @(Get-Process python -ErrorAction SilentlyContinue)

Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '  Trae2api-cn - current processes' -ForegroundColor White
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray

if ($relayPids)  { Write-Host ("  relay  (8000): PID " + ($relayPids -join ', ')) } else { Write-Host '  relay  (8000): not running' }
if ($helperPids) { Write-Host ("  helper (8765): PID " + ($helperPids -join ', ')) } else { Write-Host '  helper (8765): not running' }
if ($cfProcs)    { Write-Host ("  tunnel      : PID " + (($cfProcs | ForEach-Object { $_.Id }) -join ', ')) } else { Write-Host '  tunnel      : not running' }

if ($ListOnly) { exit 0 }

Write-Host ''
Write-Host '  stopping ...' -ForegroundColor Yellow

$targets = @($relayPids + $helperPids | Select-Object -Unique | Where-Object { $_ })
foreach ($procId in $targets) {
    try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "  stopped PID $procId" }
    catch { Write-Host "  could not stop PID $procId : $($_.Exception.Message)" -ForegroundColor DarkYellow }
}
$cfProcs | ForEach-Object {
    try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; Write-Host "  stopped cloudflared $($_.Id)" }
    catch { Write-Host "  could not stop cloudflared $($_.Id)" -ForegroundColor DarkYellow }
}

Start-Sleep -Milliseconds 800
$still = @()
if (Get-PortOwners 8000)  { $still += '8000' }
if (Get-PortOwners 8765)  { $still += '8765' }
if ($still.Count -eq 0) { Write-Host '  all stopped.' -ForegroundColor Green }
else { Write-Host ("  still listening: " + ($still -join ', ')) -ForegroundColor Yellow }
