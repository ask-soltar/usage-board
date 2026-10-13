# One-time setup for the usage board reader (Windows).
# From this folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
param([switch]$SkipLogin)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }

Step "1/6 Checking Python"
$py = $null
foreach ($c in @("py", "python")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $a = @(); if ($c -eq "py") { $a = @("-3") }
        & $c @a -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; $pyArgs = $a; break }
    }
}
if (-not $py) {
    Write-Host "Python was not found. Run:  winget install Python.Python.3.12"
    Write-Host "Then open a NEW PowerShell window and run this script again."
    exit 1
}
& $py @pyArgs --version

Step "2/6 Installing Python packages"
& $py @pyArgs -m pip install --quiet --upgrade playwright requests
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Step "3/6 Checking Google Chrome"
$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw "Google Chrome was not found. Install it from google.com/chrome and run this script again." }
Write-Host "Found Chrome."

Step "4/6 Git identity and GLM key"
if (-not (git config user.email)) {
    git config user.email "luckifyme@gmail.com"
    git config user.name "Preston Lee"
}
$existing = [Environment]::GetEnvironmentVariable("GLM_API_KEY", "User")
if ($existing) {
    $env:GLM_API_KEY = $existing
    Write-Host "GLM_API_KEY is already set."
} else {
    Write-Host "ChatGPT's page is read by GLM, so a Z.ai API key is needed for that card."
    $sec = Read-Host "Paste your Z.ai API key (hidden), or press Enter to skip" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    if ($plain) {
        [Environment]::SetEnvironmentVariable("GLM_API_KEY", $plain, "User")
        $env:GLM_API_KEY = $plain
        Write-Host "Saved to your Windows user environment only."
    } else {
        Write-Host "Skipped. Gemini and GLM will still work; ChatGPT will not."
    }
}

Step "5/6 Sign in once"
if ($SkipLogin) {
    Write-Host "Skipping sign-in (already done)."
} else {
    Write-Host "A Chrome window opens with three tabs: ChatGPT, Gemini and Z.ai."
    Write-Host "Sign in to each one yourself, then come back here and press Enter."
    & $py @pyArgs reader\read_usage.py login
    if ($LASTEXITCODE -ne 0) { throw "Sign-in step failed" }
}

Step "6/6 First reading, then schedule"
& $py @pyArgs reader\read_usage.py run
if ($LASTEXITCODE -ne 0) {
    Write-Host "The first run did not finish cleanly (see above). Fix that, then run this script again." -ForegroundColor Yellow
    exit 1
}
$pyExe = (& $py @pyArgs -c "import sys;print(sys.executable)").Trim()
$pyw = $pyExe -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $pyExe }
$action = New-ScheduledTaskAction -Execute $pyw -Argument "reader\read_usage.py run" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "UsageBoard" -Action $action -Trigger $trigger -Settings $settings -Description "Refreshes the usage board every 2 hours" -Force | Out-Null

Write-Host ""
Write-Host "Done. The board refreshes every 2 hours while this PC is on." -ForegroundColor Green
Write-Host "Live page: https://ask-soltar.github.io/usage-board/  (give it a minute after a push)"
Write-Host "Log of scheduled runs: reader\last_run.log"
Write-Host "To stop the schedule:  Unregister-ScheduledTask -TaskName UsageBoard -Confirm:`$false"
