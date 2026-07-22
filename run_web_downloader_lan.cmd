@echo off
cd /d "%~dp0"
set "VIDEOGET_HOST=0.0.0.0"
set "VIDEOGET_PORT=8787"
set "VIDEOGET_DOWNLOAD_DIR=%USERPROFILE%\video-downloader"
set "VIDEOGET_CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "VIDEOGET_CHROME_PROFILE_DIR=%~dp0chrome_profile"

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

echo Starting VideoGet for LAN testing...
echo Local: http://127.0.0.1:%VIDEOGET_PORT%
if defined LAN_IP echo LAN:   http://%LAN_IP%:%VIDEOGET_PORT%
echo.
echo If another device cannot open it, allow Python in Windows Firewall for Private networks.
"%PYTHON_EXE%" "%~dp0web_downloader_app.py"
