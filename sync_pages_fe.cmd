@echo off
cd /d "%~dp0"
if not exist "%~dp0docs" mkdir "%~dp0docs"
copy /y "%~dp0web_static\index.html" "%~dp0docs\index.html" >nul
copy /y "%~dp0web_static\styles.css" "%~dp0docs\styles.css" >nul
copy /y "%~dp0web_static\client.js" "%~dp0docs\client.js" >nul
if not exist "%~dp0docs\.nojekyll" type nul > "%~dp0docs\.nojekyll"
echo GitHub Pages client FE synced to docs\
