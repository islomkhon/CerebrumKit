# CerebrumKit Launcher
# Starts both the FastAPI backend and Vue frontend

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend\cerebrumkit-vue"
$PythonExe = Join-Path $BackendDir "venv\Scripts\python.exe"

# Never assign to $pid/$PID, $host, $error, $args or $input: they are read-only
# automatic variables in PowerShell. Doing so threw an error that aborted this
# script, and the following taskkill then killed the launcher's own window.
function Clear-Port {
    param([int]$Port)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) { return }

    foreach ($listener in $listeners) {
        $ownerPid = $listener.OwningProcess
        if (-not $ownerPid -or $ownerPid -eq $PID) { continue }
        Write-Host "  [~] Freeing port $Port (stale PID $ownerPid)" -ForegroundColor DarkYellow
        taskkill /F /T /PID $ownerPid 2>$null | Out-Null
    }
    Start-Sleep -Seconds 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CerebrumKit Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Backend ──
# Free both ports first so the advertised URLs are the ones actually used
Clear-Port -Port 8000
Clear-Port -Port 5173

Write-Host "[1/2] Starting FastAPI backend..." -ForegroundColor Yellow
$BackendLog = Join-Path $Root "backend.log"
$BackendJob = Start-Job -Name "cerebrumkit-backend" -ScriptBlock {
    param($Dir, $Log, $Python)
    Set-Location $Dir
    $env:PYTHONUNBUFFERED = 1
    if ($Python -and (Test-Path $Python)) {
        & $Python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 |
            Out-File -FilePath $Log -Encoding utf8 -Append
    } else {
        uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 |
            Out-File -FilePath $Log -Encoding utf8 -Append
    }
} -ArgumentList $BackendDir, $BackendLog, $PythonExe

Start-Sleep -Seconds 2
$bj = $BackendJob | Receive-Job
Write-Host "   Backend process ID: $($BackendJob.Id)" -ForegroundColor Green
Write-Host "   API: http://localhost:8000" -ForegroundColor Green
Write-Host "   Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "   Log: $BackendLog" -ForegroundColor DarkGray
if ($bj) { Write-Host "   $bj" -ForegroundColor DarkGray }

# ── Frontend ──
Write-Host ""
Write-Host "[2/2] Starting Vue frontend..." -ForegroundColor Yellow
$FrontendLog = Join-Path $Root "frontend.log"
$FrontendJob = Start-Job -Name "cerebrumkit-frontend" -ScriptBlock {
    param($Dir, $Log)
    Set-Location $Dir
    npm run dev 2>&1 | Out-File -FilePath $Log -Encoding utf8 -Append
} -ArgumentList $FrontendDir, $FrontendLog

Start-Sleep -Seconds 4
$fj = $FrontendJob | Receive-Job
Write-Host "   Frontend process ID: $($FrontendJob.Id)" -ForegroundColor Green
Write-Host "   URL: http://localhost:5173" -ForegroundColor Green
Write-Host "   Log: $FrontendLog" -ForegroundColor DarkGray
if ($fj) { Write-Host "   $fj" -ForegroundColor DarkGray }

# ── Summary ──
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Both services started!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend  → http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs → http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Frontend → http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "  Stop with:  Stop-Job cerebrumkit-backend, cerebrumkit-frontend" -ForegroundColor DarkYellow
Write-Host "  Or just:    .\stop.ps1" -ForegroundColor DarkYellow
Write-Host ""

# Keep script alive so the window stays open
Write-Host "Press Ctrl+C to stop both processes..." -ForegroundColor DarkGray
while ($true) {
    Start-Sleep -Seconds 5

    # Check if jobs are still alive
    $b = Get-Job -Name "cerebrumkit-backend" -ErrorAction SilentlyContinue
    $f = Get-Job -Name "cerebrumkit-frontend" -ErrorAction SilentlyContinue

    if (-not $b -and -not $f) {
        Write-Host "Both processes have stopped. Exiting." -ForegroundColor Red
        break
    }
    if (-not $b) {
        Write-Host "Backend process has stopped." -ForegroundColor Red
    }
    if (-not $f) {
        Write-Host "Frontend process has stopped." -ForegroundColor Red
    }
}
