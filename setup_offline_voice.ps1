# Install optional offline speech recognition without OpenAI API keys.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'First run run.cmd once to create .venv, then rerun this script.' }
& $python -m pip install 'faster-whisper>=1.1,<2'
if ($LASTEXITCODE -ne 0) { throw 'Offline speech package installation failed.' }
Write-Host 'Installed local speech recognition. First transcription will download its language model (internet required once).' -ForegroundColor Green
Write-Host 'Restart run.cmd, leave STT_PROVIDER=auto or set STT_PROVIDER=local in .env.' -ForegroundColor Yellow
