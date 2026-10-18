# setup.ps1 - install relay dependencies into <repo>\relay-deps and seed .env
#
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Python "D:\Python312\python.exe"

param([string]$Python = '')

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot  = Split-Path -Parent $ScriptDir
$Req       = Join-Path $RepoRoot 'relay\requirements.txt'
$Deps      = Join-Path $RepoRoot 'relay-deps'
$EnvFile   = Join-Path $RepoRoot 'relay\.env'
$EnvSample = Join-Path $RepoRoot 'relay\.env.example'

Write-Host '============================================================' -ForegroundColor DarkGray
Write-Host '  Trae relay setup' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor DarkGray

# ---- locate python ----
$candidates = @()
if ($Python) { $candidates += $Python }
$candidates += @(
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    (Get-Command python3 -ErrorAction SilentlyContinue).Source,
    'C:\Python313\python.exe',
    'C:\Python312\python.exe',
    'C:\Python311\python.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\vbox\pyruntime\python.exe')
) | Where-Object { $_ }

$py = $null
foreach ($c in $candidates) {
    if (-not (Test-Path $c)) { continue }
    $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) {
        $parts = $v.Split('.')
        if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) { $py = $c; break }
    }
}
if (-not $py) {
    Write-Host '[ERROR] Python 3.11+ not found. Install it from python.org and re-run.' -ForegroundColor Red
    exit 1
}
Write-Host "  python : $py"

# ---- install deps ----
if (-not (Test-Path $Req)) { Write-Host "[ERROR] missing $Req" -ForegroundColor Red; exit 1 }
if (Test-Path $Deps) { Remove-Item $Deps -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host '  installing dependencies ...' -ForegroundColor Cyan
& $py -m pip install --no-cache-dir --target $Deps -r $Req
if ($LASTEXITCODE -ne 0) {
    Write-Host '  retrying with the Aliyun mirror ...' -ForegroundColor Yellow
    & $py -m pip install --no-cache-dir --target $Deps -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r $Req
}
if ($LASTEXITCODE -ne 0) { Write-Host '[ERROR] dependency install failed' -ForegroundColor Red; exit 1 }

$env:PYTHONPATH = $Deps
& $py -c "import fastapi, uvicorn, httpx, cryptography, dotenv; print('  deps ok')"
if ($LASTEXITCODE -ne 0) { Write-Host '[ERROR] import check failed' -ForegroundColor Red; exit 1 }

# ---- seed .env ----
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvSample) {
        Copy-Item $EnvSample $EnvFile
        Write-Host "  created : $EnvFile" -ForegroundColor Green
        Write-Host '  edit it and set RELAY_API_KEYS + TRAE_AUTH_SOURCE before starting.' -ForegroundColor Yellow
    }
} else {
    Write-Host "  .env exists, left untouched"
}

Write-Host ''
Write-Host '  next:  .\start-all.bat' -ForegroundColor Green
