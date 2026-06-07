$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CodexPython = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $CodexPython) {
    $Python = $CodexPython
} else {
    $Python = "python"
}

Set-Location $ProjectRoot

Write-Host "Starting FluffyGo backend API on http://127.0.0.1:8001 ..."
Start-Process -FilePath $Python `
    -ArgumentList "api_server.py" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

Start-Sleep -Seconds 2

Write-Host "Starting FluffyGo frontend on http://127.0.0.1:8000/stitch_demo.html ..."
Start-Process -FilePath $Python `
    -ArgumentList "-m http.server 8000 --bind 127.0.0.1" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

Write-Host ""
Write-Host "FluffyGo Demo is starting."
Write-Host "Frontend: http://127.0.0.1:8000/stitch_demo.html"
Write-Host "Backend health: http://127.0.0.1:8001/api/health"
Write-Host ""
Write-Host "If a port is already in use, close the old python process or change the port."
