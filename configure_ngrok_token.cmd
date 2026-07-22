@echo off
set "NGROK_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\ngrok.exe"
if not exist "%NGROK_EXE%" (
  echo ngrok.exe not found at %NGROK_EXE%
  echo Open Microsoft Store ngrok once, or reinstall ngrok.
  exit /b 1
)

set /p NGROK_TOKEN=Paste your ngrok authtoken: 
"%NGROK_EXE%" config add-authtoken %NGROK_TOKEN%
set "NGROK_TOKEN="
echo ngrok authtoken configured.
