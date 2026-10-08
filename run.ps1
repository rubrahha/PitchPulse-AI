# Windows PowerShell 5.1+ launcher. Local loopback binding only.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env. Add your OpenAI, cricket and football API keys for complete functionality." -ForegroundColor Yellow
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3.12 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw "Python 3.12 required. Install stable Python 3.12 and retry." }
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check your internet connection." }
$env:PYTHONUTF8 = "1"
$url = "http://127.0.0.1:8000"
Write-Host "Starting PitchPulse AI locally..." -ForegroundColor Cyan
$server = Start-Process -FilePath $python -ArgumentList @("-m","uvicorn","sportpulse.main:app","--host","127.0.0.1","--port","8000") -PassThru -NoNewWindow
try {
  $ready = $false
  for ($i = 0; $i -lt 45; $i++) {
    if ($server.HasExited) { throw "The server stopped before it was ready." }
    try {
      $response = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 1
      if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 250 }
  }
  if (-not $ready) { throw "The app did not start within the expected time. Is port 8000 busy?" }
  Write-Host "Ready at $url  (close this terminal to stop the server)" -ForegroundColor Green
  Start-Process $url
  Wait-Process -Id $server.Id
} finally {
  if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}
