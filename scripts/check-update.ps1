# check-update.ps1 - compare the locally running relay version with the newest
# GitHub release of autumnsentiment/Trae2api-cn.
# Usage: double-click check-update.bat

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$MainPy = Join-Path $Root 'Trae2api-cn\Trae2api-cn-main\src\main.py'

Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '  Trae2api-cn - update check' -ForegroundColor White
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray

$local = 'unknown'
if (Test-Path $MainPy) {
    $m = Select-String -Path $MainPy -Pattern '^APP_VERSION\s*=\s*"([^"]+)"' -ErrorAction SilentlyContinue
    if ($m) { $local = $m.Matches[0].Groups[1].Value }
}
Write-Host "  local version : $local"

$remoteTag = $null
try {
    $rel = Invoke-RestMethod 'https://api.github.com/repos/autumnsentiment/Trae2api-cn/releases/latest' `
        -TimeoutSec 20 -Headers @{ 'User-Agent' = 'trae-relay-check' }
    $remoteTag = $rel.tag_name
    Write-Host "  newest release: $remoteTag  ($($rel.published_at))"
} catch {
    Write-Host "  could not reach GitHub: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host '  (network blocked, or GitHub API rate limited)' -ForegroundColor DarkGray
    exit 1
}

$remote = $remoteTag -replace '^v', ''
if ($local -eq $remote) {
    Write-Host ''
    Write-Host '  Already up to date.' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host "  New version available: $local -> $remote" -ForegroundColor Yellow
    Write-Host ''
    Write-Host '  How to update (keeps your .env / data):'
    Write-Host '    1) download  https://codeload.github.com/autumnsentiment/Trae2api-cn/zip/refs/heads/main'
    Write-Host '    2) back up  src\main.py, src\sse.py, .env  and  data\'
    Write-Host '    3) replace Trae2api-cn\Trae2api-cn-main\src with the new src'
    Write-Host '    4) re-apply the local patches listed in Trae2api-cn-使用手册.md section 11'
    Write-Host '    5) restart with start-all.bat'
}

Write-Host ''
Write-Host '  Note: the console itself does NOT poll for updates;' -ForegroundColor DarkGray
Write-Host '  this script is the only check.' -ForegroundColor DarkGray
