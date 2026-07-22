@echo off
cd /d "%~dp0"
set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\ngrok.exe"
if not exist "%NGROK_EXE%" (
  echo ngrok.exe not found at %NGROK_EXE%
  echo Open Microsoft Store ngrok once, or reinstall ngrok.
  exit /b 1
)

echo Starting ngrok tunnel for VideoGet API...
echo Local API: http://127.0.0.1:8787
echo Dashboard: http://127.0.0.1:4040
echo.
if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
if not exist "%~dp0logs" mkdir "%~dp0logs"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ngrok=$env:NGROK_EXE; $runtime=Join-Path (Get-Location) '.runtime'; $log=Join-Path (Get-Location) 'logs\ngrok.out.log'; & $ngrok http 8787 2>&1 | ForEach-Object { $line = $_.ToString(); $line; Add-Content -Path $log -Value $line; if ($line -match 'https://[a-zA-Z0-9.-]+\.ngrok(?:-free)?\.(?:app|dev)') { $matches[0] | Set-Content -Path (Join-Path $runtime 'ngrok_url.txt') } }"
