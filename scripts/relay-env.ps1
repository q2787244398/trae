# relay-env.ps1 - resolve a usable Python interpreter and the dependency folder.
# Dot-source it:   . "$PSScriptRoot\relay-env.ps1"
# Provides:        $RelayPython, $RelayDeps

$script:RelayRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition

$candidates = @(
    (Join-Path $script:RelayRoot 'relay-venv\Scripts\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\vbox\pyruntime\python.exe'),
    'C:\Python313\python.exe',
    'C:\Python312\python.exe',
    'C:\Python311\python.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
)

$script:RelayPython = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $script:RelayPython = $c; break }
}

$script:RelayDeps = Join-Path $script:RelayRoot 'relay-deps'
if (-not (Test-Path $script:RelayDeps)) {
    $venvSite = Join-Path $script:RelayRoot 'relay-venv\Lib\site-packages'
    if (Test-Path $venvSite) { $script:RelayDeps = $venvSite }
}

if ($script:RelayDeps -and (Test-Path $script:RelayDeps)) {
    $env:PYTHONPATH = $script:RelayDeps
}

if (-not $script:RelayPython) {
    Write-Host '[ERROR] no Python found. Install Python 3.11+ or place relay-venv next to this script.' -ForegroundColor Red
}
