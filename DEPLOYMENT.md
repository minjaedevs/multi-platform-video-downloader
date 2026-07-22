# Video Downloader MCP Deployment Guide

This project runs as a stdio MCP server. It does not expose an HTTP port by
default; an MCP client starts `server.py` and talks to it over stdin/stdout.

## Local Windows Setup

From the project folder:

```powershell
cd D:\be_video_downloader_mcp
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you also want to run tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q test_security.py test_mcp_protocol_basic.py test_mcp_security.py
```

Verify that yt-dlp is available:

```powershell
.\.venv\Scripts\python.exe -m yt_dlp --version
```

## MCP Client Configuration

Use the venv Python path directly so the client always gets the installed
dependencies:

```json
{
  "mcpServers": {
    "video-downloader": {
      "command": "D:\\be_video_downloader_mcp\\.venv\\Scripts\\python.exe",
      "args": ["D:\\be_video_downloader_mcp\\server.py"]
    }
  }
}
```

Restart the MCP client after editing its configuration.

## Download Configuration

On first run, the server creates:

```text
C:\Users\Pc\.config\video-downloader-mcp\config.toml
```

The default download location is:

```text
C:\Users\Pc\video-downloader
```

Add or change locations in the config file:

```toml
[download_locations]
default = "~/video-downloader"
downloads = "~/Downloads/videos"
archive = "D:/sports_data/video-archive"
```

Keep `enforce_location_restrictions = true` for normal use so agents can only
write into configured directories.

## Linux Server Deployment

On a Linux VM:

```bash
git clone https://github.com/chazmaniandinkle/video-downloader-mcp.git
cd video-downloader-mcp
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m yt_dlp --version
```

MCP client config:

```json
{
  "mcpServers": {
    "video-downloader": {
      "command": "/opt/video-downloader-mcp/.venv/bin/python",
      "args": ["/opt/video-downloader-mcp/server.py"]
    }
  }
}
```

This server is best deployed on the same machine as the MCP client, because
stdio MCP servers are launched as child processes. For a remote setup, run the
MCP client or an MCP proxy on the server and point it at this command.

## Operational Notes

- Keep `yt-dlp` updated because site extractors change often:
  `.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp`
- Install `ffmpeg` for better video/audio merging. This machine already has
  `ffmpeg` available in PATH.
- Some real download tests depend on external sites and can hang or fail when a
  site blocks requests. Prefer testing with a URL you control.
