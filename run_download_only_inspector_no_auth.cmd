@echo off
cd /d D:\be_video_downloader_mcp
set "DANGEROUSLY_OMIT_AUTH=true"
npx.cmd -y @modelcontextprotocol/inspector --transport stdio D:/be_video_downloader_mcp/.venv/Scripts/python.exe D:/be_video_downloader_mcp/download_only_server.py
