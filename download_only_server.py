#!/usr/bin/env python3
"""Download-only MCP server backed by yt-dlp.

Downloads run in the background so MCP clients such as Inspector do not time out
while yt-dlp is still fetching or merging media.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP(
    "video-downloader",
    instructions="Download videos from platforms supported by yt-dlp.",
)

DEFAULT_DOWNLOAD_DIR = Path.home() / "video-downloader"
DEFAULT_LOG_DIR = DEFAULT_DOWNLOAD_DIR / "_logs"

jobs: dict[str, dict[str, Any]] = {}


def _yt_dlp_command() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _safe_output_dir(path: str | None) -> Path:
    raw_path = Path(os.path.expanduser(path or str(DEFAULT_DOWNLOAD_DIR)))
    output_dir = raw_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _read_tail(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _build_command(
    url: str,
    output_dir: Path,
    format_id: str,
    audio_only: bool,
    allow_playlist: bool,
    dry_run: bool,
) -> list[str]:
    output_template = "%(title).200B [%(id)s].%(ext)s"
    cmd = _yt_dlp_command()

    if dry_run:
        cmd.extend(["--simulate", "--print", "title"])

    if not allow_playlist:
        cmd.append("--no-playlist")

    if audio_only:
        cmd.extend(["-x", "--audio-format", "mp3"])
    else:
        cmd.extend(["-f", format_id])

    cmd.extend(["-P", str(output_dir), "-o", output_template, url])
    return cmd


def _snapshot_job(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    process: subprocess.Popen[str] = job["process"]
    return_code = process.poll()
    status = "running" if return_code is None else ("completed" if return_code == 0 else "failed")
    return {
        "job_id": job_id,
        "status": status,
        "return_code": return_code,
        "url": job["url"],
        "dry_run": job["dry_run"],
        "output_dir": job["output_dir"],
        "log_file": job["log_file"],
        "started_at": job["started_at"],
        "command": job["command"],
        "log_tail": _read_tail(Path(job["log_file"])),
    }


@mcp.tool()
def download_video(
    url: str,
    format_id: str = "bestvideo+bestaudio/best",
    output_dir: str | None = None,
    audio_only: bool = False,
    allow_playlist: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Start a video download job and return immediately.

    Set dry_run=true to test extraction without downloading media.
    Use only for videos you own or have permission to download.
    """
    if not url.startswith(("http://", "https://")):
        return {"success": False, "error": "url must start with http:// or https://"}

    target_dir = _safe_output_dir(output_dir)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    log_file = DEFAULT_LOG_DIR / f"{job_id}.log"
    cmd = _build_command(url, target_dir, format_id, audio_only, allow_playlist, dry_run)

    log_handle = log_file.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path(__file__).parent),
    )
    log_handle.close()

    jobs[job_id] = {
        "process": process,
        "url": url,
        "dry_run": dry_run,
        "output_dir": str(target_dir),
        "log_file": str(log_file),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": cmd,
    }

    return {
        "success": True,
        "job_id": job_id,
        "status": "running",
        "dry_run": dry_run,
        "output_dir": str(target_dir),
        "log_file": str(log_file),
        "next_step": "Call get_download_status with this job_id.",
    }


@mcp.tool()
def get_download_status(job_id: str) -> dict[str, Any]:
    """Get status and recent yt-dlp log output for a download job."""
    job = jobs.get(job_id)
    if not job:
        return {"success": False, "error": f"Unknown job_id: {job_id}"}
    return {"success": True, **_snapshot_job(job_id, job)}


@mcp.tool()
def cancel_download(job_id: str) -> dict[str, Any]:
    """Cancel a running download job."""
    job = jobs.get(job_id)
    if not job:
        return {"success": False, "error": f"Unknown job_id: {job_id}"}

    process: subprocess.Popen[str] = job["process"]
    if process.poll() is None:
        process.terminate()
        return {"success": True, "job_id": job_id, "status": "terminating"}

    return {"success": True, "job_id": job_id, "status": "already_finished"}


@mcp.tool()
def get_download_folder() -> dict[str, Any]:
    """Return the default download folder."""
    DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "success": True,
        "download_dir": str(DEFAULT_DOWNLOAD_DIR),
        "log_dir": str(DEFAULT_LOG_DIR),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
