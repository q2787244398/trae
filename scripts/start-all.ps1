# start-all.ps1 - one-click launcher for the local Trae2api-cn relay.
# Starts: relay (127.0.0.1:8000) -> Cloudflare quick tunnel -> local auth helper.
# Writes the fresh public console URL to the Desktop.
# Run via start-all.bat (double-click) or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\start-all.ps1

param([switch]$NoTunnel)

$ErrorActionPreference = 'Stop'
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$App    = Join-Path $Root 'Trae2api-cn\Trae2api-cn-main'
$Cf     = Join-Path $Root 'tools\cloudflared.exe'
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

. (Join-Path $Root 'relay-env.ps1')
$Py = $RelayPython

function Test-Port([int]$Port) {
    try { return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop) }
    catch { return $false }
}

function Write-Step($Text) { Write-Host $Text -ForegroundColor Cyan }

Write-Host '============================================================' -ForegroundColor DarkGray
Write-Host '  Trae2api-cn launcher' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor DarkGray

if (-not $Py) { Write-Host '[ERROR] no Python interpreter found (see relay-env.ps1)' -ForegroundColor Red; exit 1 }
if (-not (Test-Path $Cf)) { Write-Host "[ERROR] cloudflared not found: $Cf" -ForegroundColor Red; exit 1 }

# ---------- 1) relay ----------
if (-not (Test-Port 8000)) {
    Write-Step '[1/3] starting relay on 127.0.0.1:8000 ...'
    Start-Process -FilePath $Py `
        -ArgumentList '-m','uvicorn','src.main:app','--host','127.0.0.1','--port','8000','--log-level','warning' `
        -WorkingDirectory $App -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'relay.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'relay.err.log')
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Port 8000) { break }
    }
    if (-not (Test-Port 8000)) { Write-Host '[ERROR] relay did not come up; see logs\relay.err.log' -ForegroundColor Red; exit 1 }
} else {
    Write-Step '[1/3] relay already listening on 8000 - skipped'
}

# ---------- 2) cloudflare quick tunnel ----------
$url = $null
if ($NoTunnel) {
    Write-Step '[2/3] tunnel skipped (-NoTunnel)'
} else {
Write-Step '[2/3] starting Cloudflare tunnel ...'
$tunLog = Join-Path $LogDir 'tunnel.log'
if (Test-Path $tunLog) { Remove-Item $tunLog -Force -ErrorAction SilentlyContinue }
Start-Process -FilePath $Cf -ArgumentList 'tunnel','--url','http://127.0.0.1:8000','--no-autoupdate' `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir 'tunnel.out.log') `
    -RedirectStandardError $tunLog

for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 1000
    if (Test-Path $tunLog) {
        $hit = Select-String -Path $tunLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue
        if ($hit -and $hit.Matches.Count -gt 0) { $url = $hit.Matches[0].Value; break }
    }
}
}

$desktop = Join-Path $env:USERPROFILE 'Desktop'
if (-not (Test-Path $desktop)) { $desktop = Join-Path $env:USERPROFILE 'OneDrive\Desktop' }
if (-not (Test-Path $desktop)) { $desktop = $Root }
$urlFile = Join-Path $desktop 'trae-relay-url.txt'

if (-not $url) {
    Write-Host '[WARN] could not read the tunnel URL yet - check logs\tunnel.log' -ForegroundColor Yellow
} else {
    "$url/web/login" | Set-Content -Path $urlFile -Encoding ASCII

    # Ready-to-paste iSH one-liner for authorizing an extra account on iPhone.
    $pwdFile = Join-Path $Root 'relay-admin-password.txt'
    $adminPwd = if (Test-Path $pwdFile) { (Get-Content $pwdFile -Raw).Trim() } else { '' }
    if ($adminPwd) {
        $pyLine = 'apk add --no-cache python3 ca-certificates >/dev/null 2>&1; python3 -c "import base64,urllib.request as u;r=u.Request(''' + $url + '/web/login/download?as=py'');r.add_header(''Authorization'',''Basic ''+base64.b64encode(b''admin:' + $adminPwd + ''').decode());open(''/tmp/trae_login.py'',''wb'').write(u.urlopen(r,timeout=30).read())" && python3 /tmp/trae_login.py'
        $iosFile = Join-Path $desktop 'trae-iphone-login.txt'
        @(
            '# iPhone (iSH) 新增账号授权：把下面这一整行复制到 iSH 里回车即可',
            '# 打开 iSH -> 长按粘贴 -> 回车，出现「本地监听 8765」后回 Safari 点授权',
            '',
            $pyLine,
            '',
            '# 如果报 SSL/证书错误，用这一行（跳过证书校验）：',
            ($pyLine -replace [regex]::Escape("u.urlopen(r,timeout=30).read()"), "u.urlopen(r,timeout=30,context=__import__('ssl')._create_unverified_context()).read()")
        ) | Set-Content -Path $iosFile -Encoding UTF8
        Write-Host "  iPhone cmd     : $iosFile" -ForegroundColor Green
    }

    Write-Host ''
    Write-Host "  Public console : $url/web/login" -ForegroundColor Green
    Write-Host "  Saved to       : $urlFile" -ForegroundColor Green
}

# ---------- 3) auth helper ----------
if (-not (Test-Port 8765)) {
    Write-Step '[3/3] starting local auth helper on 127.0.0.1:8765 ...'
    Start-Process -FilePath $Py -ArgumentList 'web_login.py','--relay','http://127.0.0.1:8000','--no-open' `
        -WorkingDirectory $App -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'helper.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'helper.err.log')
    Start-Sleep -Milliseconds 1500
    if (Test-Port 8765) { Write-Host '      helper ready (used only for PC-side Trae login)' -ForegroundColor DarkGray }
    else { Write-Host '      helper did not bind 8765 - see logs\helper.err.log' -ForegroundColor Yellow }
} else {
    Write-Step '[3/3] auth helper already listening on 8765 - skipped'
}

Write-Host ''
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '  console user : admin'
Write-Host '  password     : relay-admin-password.txt'
Write-Host '  API key      : relay-api-key.txt'
Write-Host "  logs         : $LogDir"
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
Write-Host '  NOTE: the quick-tunnel URL changes on every run.' -ForegroundColor Yellow
Write-Host '  A stable address needs your own domain + a named tunnel.' -ForegroundColor Yellow
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray
