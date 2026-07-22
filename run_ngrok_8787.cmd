@echo off
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
"%NGROK_EXE%" http 8787
