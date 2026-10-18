# launcher.ps1 - one small window with every Trae Relay action.
# Add new entries to $Actions below; the window builds itself from the list.

param([switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$App  = Join-Path $Root 'Trae2api-cn\Trae2api-cn-main'
$Py   = Join-Path $Root 'relay-venv\Scripts\python.exe'
$UrlFile = Join-Path $env:USERPROFILE 'Desktop\trae-relay-url.txt'
if (-not (Test-Path $UrlFile)) { $UrlFile = Join-Path $env:USERPROFILE 'OneDrive\Desktop\trae-relay-url.txt' }

# ---------------- action list (extend here) ----------------
$Actions = @(
    @{ Text = '▶  启动';        Kind = 'script'; Path = 'start-all.ps1';    Hint = '启动 relay + 隧道 + 助手' }
    @{ Text = '⟳  重启';        Kind = 'script'; Path = 'restart-all.ps1';  Hint = '修改 .env 后用它生效' }
    @{ Text = '■  停止';        Kind = 'script'; Path = 'stop-all.ps1';     Hint = '停止全部进程' }
    @{ Text = '🌐  打开控制台';  Kind = 'url';    Value = 'http://127.0.0.1:8000/web/login'; Hint = '本机控制台' }
    @{ Text = '🔑  导出本机凭据'; Kind = 'script'; Path = 'dump-token.ps1';   Hint = '从 Trae 客户端读出 token' }
    @{ Text = '🔄  检查更新';    Kind = 'script'; Path = 'check-update.ps1'; Hint = '对比 GitHub 最新版本' }
    @{ Text = '📄  打开日志目录'; Kind = 'folder'; Value = 'logs';            Hint = 'relay / tunnel 日志' }
    @{ Text = '✕  退出';        Kind = 'exit';                              Hint = '关闭此窗口' }
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Trae Relay 控制台'
$form.ClientSize = New-Object System.Drawing.Size(360, 486)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Trae CN Relay'
$title.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 13, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(16, 12)
$title.AutoSize = $true
$form.Controls.Add($title)

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(18, 44)
$status.Size = New-Object System.Drawing.Size(324, 62)
$status.ForeColor = [System.Drawing.Color]::FromArgb(70, 70, 70)
$form.Controls.Add($status)

$y = 116
foreach ($a in $Actions) {
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $a.Text
    $btn.TextAlign = 'MiddleLeft'
    $btn.Padding = New-Object System.Windows.Forms.Padding(10, 0, 0, 0)
    $btn.Location = New-Object System.Drawing.Point(18, $y)
    $btn.Size = New-Object System.Drawing.Size(324, 34)
    $btn.Tag = $a
    $btn.Add_Click({
        param($sender, $e)
        $act = $sender.Tag
        try {
            switch ($act.Kind) {
                'script' {
                    Start-Process -FilePath 'powershell' -ArgumentList @(
                        '-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File',(Join-Path $Root $act.Path)
                    ) -WorkingDirectory $Root | Out-Null
                }
                'url'    { Start-Process $act.Value | Out-Null }
                'folder' { Start-Process explorer.exe (Join-Path $Root $act.Value) | Out-Null }
                'exit'   { $form.Close() }
            }
            Start-Sleep -Milliseconds 600
            Update-Status
        } catch {
            [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, '出错了') | Out-Null
        }
    })
    $form.Controls.Add($btn)
    $y += 40
}

function Get-PortUp([int]$Port) {
    try { return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop) } catch { return $false }
}

function Update-Status {
    $relay  = Get-PortUp 8000
    $helper = Get-PortUp 8765
    $tunnel = [bool](Get-Process cloudflared -ErrorAction SilentlyContinue)
    $url = ''
    if (Test-Path $UrlFile) { $url = (Get-Content $UrlFile -TotalCount 1) }
    $lines = @()
    $lines += "relay : " + $(if ($relay) { '运行中 (8000)' } else { '未运行' })
    $lines += "隧道  : " + $(if ($tunnel) { '已连接' } else { '未连接' }) + "    助手: " + $(if ($helper) { '在线' } else { '离线' })
    if ($url) { $lines += "地址  : $url" }
    $status.Text = ($lines -join "`r`n")
    $status.ForeColor = if ($relay) { [System.Drawing.Color]::FromArgb(30, 120, 60) } else { [System.Drawing.Color]::FromArgb(150, 60, 60) }
}

Update-Status
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 3000
$timer.Add_Tick({ Update-Status })
$timer.Start()

if ($SmokeTest) {
    Write-Host 'SMOKE OK'
    Write-Host ("buttons=" + ($Actions.Count))
    Write-Host ("status=" + $status.Text.Replace("`r`n", ' | '))
    exit 0
}

[void]$form.ShowDialog()
