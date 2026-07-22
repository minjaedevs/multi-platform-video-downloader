@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  set "PYTHON_EXE=%LOCALAPPDATA%\Python\bin\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m pip install -r requirements.txt aiohttp
