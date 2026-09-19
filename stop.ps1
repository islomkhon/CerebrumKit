# CerebrumKit Stopper

Write-Host "Stopping CerebrumKit processes..." -ForegroundColor Yellow

# Never assign to $pid/$PID, $host, $error, $args or $input: they are read-only
# automatic variables in PowerShell. Doing so threw an error that aborted this
# script, and the following taskkill then killed the stopper's own window.
function Clear-Port {
    param([int]$Port)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) { return }

    foreach ($listener in $listeners) {
        $ownerPid = $listener.OwningProcess
        if (-not $ownerPid -or $ownerPid -eq $PID) { continue }
        Write-Host "  [~] Killing stale PID $ownerPid on port $Port (and children)" -ForegroundColor DarkYellow
        taskkill /F /T /PID $ownerPid 2>$null | Out-Null
    }
}

$BackendJob = Get-Job -Name "cerebrumkit-backend" -ErrorAction SilentlyContinue
if ($BackendJob) {
    Stop-Job $BackendJob
    Remove-Job $BackendJob
    Write-Host "  [✓] Backend stopped" -ForegroundColor Green
} else {
    Write-Host "  [?] No backend job found" -ForegroundColor DarkGray
}

$FrontendJob = Get-Job -Name "cerebrumkit-frontend" -ErrorAction SilentlyContinue
if ($FrontendJob) {
    Stop-Job $FrontendJob
    Remove-Job $FrontendJob
    Write-Host "  [✓] Frontend stopped" -ForegroundColor Green
} else {
    Write-Host "  [?] No frontend job found" -ForegroundColor DarkGray
}

# Also kill any lingering uvicorn / node processes on our ports
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "vite" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Aggressively kill leftover uvicorn worker children that inherited our ports
Clear-Port -Port 8000
Clear-Port -Port 5173
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Done." -ForegroundColor Green
