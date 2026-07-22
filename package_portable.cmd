@echo off
cd /d "%~dp0"
set "DIST=%~dp0_dist"
set "PKG=%DIST%\videoget-local.zip"

if exist "%DIST%" rmdir /s /q "%DIST%"
mkdir "%DIST%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $stage=Join-Path $root '_dist\videoget-local'; New-Item -ItemType Directory -Force -Path $stage | Out-Null; $excludeDirs=@('\.git','\.venv','\chrome_profile','\_dist','\__pycache__','\.pytest_cache','\.runtime'); Get-ChildItem -Path $root -Force | Where-Object { $p=$_.FullName; -not ($excludeDirs | Where-Object { $p.Contains($_) }) } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force }; Get-ChildItem -Path $stage -Recurse -Include *.log,*.pyc,*cookies*.txt,.env,.env.*,ngrok.yml,ngrok.yaml -Force | Remove-Item -Force; Compress-Archive -Path (Join-Path $stage '*') -DestinationPath (Join-Path $root '_dist\videoget-local.zip') -Force"

echo Package created: %PKG%
