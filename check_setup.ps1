# PitchPulse AI v1.3 connectivity self-check (PowerShell 5.1+).
# Does not print or transmit your API keys.
$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"
Write-Host "PitchPulse AI local self-check" -ForegroundColor Cyan
try {
  $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 8
  Write-Host "Server: OK ($($health.version))" -ForegroundColor Green
  Write-Host "LLM configured: $($health.llm_ready)  Provider: $($health.llm_provider)"
  Write-Host "Voice fallback ready: $($health.stt_ready)  Backend: $($health.stt_backend)"
  Write-Host "Cricket scores configured: $($health.cricket_ready)"
  Write-Host "Football scores configured: $($health.football_ready)"
  $payload = '{"message":"Give me the latest cricket headlines","sport":"cricket","language":"en-IN","history":[]}'
  $reply = Invoke-RestMethod -Uri "$base/api/chat" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 50
  Write-Host "Chat API: OK - $($reply.mode)" -ForegroundColor Green
  Write-Host "Response: $($reply.answer)"
  Write-Host "Sources returned: $(@($reply.sources).Count)"
} catch {
  Write-Host "Check failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Ensure run.cmd is still open; inspect its terminal if /api/chat fails."
  exit 1
}
