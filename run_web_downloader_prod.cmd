@echo off
cd /d "%~dp0"
set "VIDEOGET_HOST=127.0.0.1"
set "VIDEOGET_PORT=8787"
set "VIDEOGET_DOWNLOAD_DIR=%~dp0processing_storage"
set "VIDEOGET_CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "VIDEOGET_CHROME_PROFILE_DIR=%~dp0chrome_profile"

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  set "PYTHON_EXE=%LOCALAPPDATA%\Python\bin\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo Starting VideoGet local...
echo Web: http://127.0.0.1:%VIDEOGET_PORT%
"%PYTHON_EXE%" "%~dp0web_downloader_app.py"
