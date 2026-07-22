@echo off
cd /d "%~dp0"
set "VIDEOGET_HOST=0.0.0.0"
set "VIDEOGET_PORT=8787"
set "VIDEOGET_DOWNLOAD_DIR=%~dp0processing_storage"
set "VIDEOGET_CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "VIDEOGET_CHROME_PROFILE_DIR=%~dp0chrome_profile"

if "%VIDEOGET_ALLOWED_ORIGINS%"=="" set "VIDEOGET_ALLOWED_ORIGINS=*"
if "%VIDEOGET_API_TOKEN%"=="" (
  for /f %%A in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"') do set "VIDEOGET_API_TOKEN=%%A"
)

if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
> "%~dp0.runtime\api_token.txt" echo %VIDEOGET_API_TOKEN%

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  set "PYTHON_EXE=%LOCALAPPDATA%\Python\bin\python.exe"
) else (
  set "PYTHON_EXE=python"
)

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IPv4"') do (
  set "LAN_IP=%%A"
  goto :got_ip
)
:got_ip
set "LAN_IP=%LAN_IP: =%"

echo Starting VideoGet public API test server...
echo Local API: http://127.0.0.1:%VIDEOGET_PORT%
if defined LAN_IP echo LAN API:   http://%LAN_IP%:%VIDEOGET_PORT%
echo API token: %VIDEOGET_API_TOKEN%
echo.
echo Public FE example:
echo https://your-frontend-domain/?api=https://your-public-api-domain^&token=%VIDEOGET_API_TOKEN%
echo.
echo Do not expose this permanently without a real reverse proxy, HTTPS, and stronger auth.
"%PYTHON_EXE%" "%~dp0web_downloader_app.py"
