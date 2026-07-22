#!/usr/bin/env python3
"""Local web UI for multi-platform video downloads."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import locale
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from aiohttp import web


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "web_static"
LOG_DIR = ROOT / "logs"
DEFAULT_DOWNLOAD_DIR = Path(os.environ.get("VIDEOGET_DOWNLOAD_DIR", ROOT / "processing_storage"))
PROCESSING_RETENTION_SECONDS = int(os.environ.get("VIDEOGET_PROCESSING_RETENTION_SECONDS", str(24 * 60 * 60)))
CHROME_EXE = Path(os.environ.get("VIDEOGET_CHROME_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
CHROME_USER_DATA_DIR = Path(os.environ.get("VIDEOGET_CHROME_PROFILE_DIR", ROOT / "chrome_profile"))
CHROME_PROFILE_DIR = CHROME_USER_DATA_DIR / "Default"
BUNDLED_BENTO4_BIN_DIR = ROOT / "tools" / "bento4" / "bin"
BENTO4_BIN_DIR = Path(os.environ.get("VIDEOGET_BENTO4_BIN_DIR", BUNDLED_BENTO4_BIN_DIR))
YOUTUBE_TEST_URL = "https://www.youtube.com/watch?v=tXv3TryZ6FA"
APP_HOST = os.environ.get("VIDEOGET_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("VIDEOGET_PORT", "8787"))
API_TOKEN = os.environ.get("VIDEOGET_API_TOKEN", "").strip()
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get("VIDEOGET_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
PLATFORM_LOGIN_URLS = {
    "youtube": "https://www.youtube.com",
    "tiktok": "https://www.tiktok.com/login",
    "facebook": "https://www.facebook.com",
    "google_drive": "https://drive.google.com",
    "direct": "https://www.google.com",
    "other": "https://www.google.com",
}

PLATFORM_COOKIE_DOMAINS = {
    "youtube": ("youtube.com", "google.com"),
    "tiktok": ("tiktok.com",),
    "facebook": ("facebook.com",),
    "google_drive": ("drive.google.com", "google.com"),
}

DIRECT_MEDIA_EXTENSIONS = {
    ".mp4",
    ".m3u8",
    ".mpd",
    ".webm",
    ".mkv",
    ".mov",
    ".avi",
    ".m4v",
    ".ts",
}

VIDEO_FILE_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".ts",
}

jobs: dict[str, dict[str, Any]] = {}

QUALITY_FORMATS = {
    "best": "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1]+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080": "bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1][height<=1080]+bestaudio/bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo*[height<=1080]+bestaudio/best[height<=1080]",
    "720": "bestvideo[ext=mp4][vcodec^=avc1][height<=720]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1][height<=720]+bestaudio/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo*[height<=720]+bestaudio/best[height<=720]",
    "480": "bestvideo[ext=mp4][vcodec^=avc1][height<=480]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1][height<=480]+bestaudio/bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/bestvideo*[height<=480]+bestaudio/best[height<=480]",
    "360": "bestvideo[ext=mp4][vcodec^=avc1][height<=360]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc1][height<=360]+bestaudio/bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/bestvideo*[height<=360]+bestaudio/best[height<=360]",
}

QUALITY_MAX_HEIGHTS = {
    "1080": 1080,
    "720": 720,
    "480": 480,
    "360": 360,
}

PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%.*?(?:of\s+(?P<size>\S+))?.*?(?:at\s+(?P<speed>\S+))?",
    re.IGNORECASE,
)
FFMPEG_TIME_RE = re.compile(r"^out_time_ms=(?P<time_ms>\d+)$")


def _decode_process_output(data: bytes) -> str:
    encodings = [
        "utf-8",
        locale.getpreferredencoding(False),
        "cp65001",
        "cp1258",
        "cp1252",
    ]
    seen: set[str] = set()
    for encoding in encodings:
        normalized = (encoding or "").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def _job_log(job: dict[str, Any] | None, event: str, message: str, *, level: str = "INFO") -> None:
    job_id = str((job or {}).get("id") or "system")
    status = str((job or {}).get("status") or "-")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[job:{job_id} time:{timestamp} status:{status} level:{level} event:{event}] {message}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "video_jobs.log").open("a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")
    except OSError:
        pass
    if job is not None:
        job.setdefault("log_lines", []).append(line)


def _job_log_progress(job: dict[str, Any], event: str, message: str, percent: float) -> None:
    bucket = int(max(0, min(100, percent)) // 10) * 10
    key = f"_logged_{event}_bucket"
    if job.get(key) == bucket:
        return
    job[key] = bucket
    _job_log(job, event, message)


def _yt_dlp_command() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _bento4_tool(name: str) -> str | None:
    exe_name = f"{name}.exe" if os.name == "nt" else name
    candidate = BENTO4_BIN_DIR / exe_name
    if candidate.exists():
        return str(candidate)
    return shutil.which(exe_name) or shutil.which(name)


def _client_id_from_request(request: web.Request) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]", "", request.headers.get("X-VideoGet-Client", ""))[:120]


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _chrome_cookies_db() -> Path:
    return CHROME_PROFILE_DIR / "Network" / "Cookies"


def _count_cookie_domains(domains: tuple[str, ...]) -> int:
    cookies_db = _chrome_cookies_db()
    if not cookies_db.exists():
        return 0

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
            temp_path = tmp.name
        shutil.copy2(cookies_db, temp_path)
        with sqlite3.connect(temp_path) as conn:
            clauses = " OR ".join(["host_key LIKE ?"] * len(domains))
            params = [f"%{domain}" for domain in domains]
            row = conn.execute(f"SELECT COUNT(*) FROM cookies WHERE {clauses}", params).fetchone()
            return int(row[0] or 0) if row else 0
    except (OSError, sqlite3.Error):
        return 0
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


async def _tool_version(cmd: list[str], timeout: int = 12) -> dict[str, Any]:
    return_code, output = await _run_command(cmd, timeout=timeout)
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    return {
        "ok": return_code == 0,
        "version": first_line,
        "message": first_line if return_code == 0 else output[-800:],
    }


def _safe_output_dir(path: str | None = None) -> Path:
    output_dir = Path(os.path.expanduser(path or str(DEFAULT_DOWNLOAD_DIR))).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _format_for_quality(quality: str) -> list[str]:
    return ["-f", QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"])]


def _quality_filename_suffix(quality: Any) -> str:
    value = str(quality or "best").strip().lower()
    if value not in QUALITY_FORMATS:
        value = "best"
    return re.sub(r"[^a-z0-9_-]", "", value) or "best"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem} ({uuid.uuid4().hex[:6]}){path.suffix}")


def _user_output_path(job: dict[str, Any], file_path: Path) -> Path:
    quality = _quality_filename_suffix(job.get("quality"))
    stem = file_path.stem
    for media_id in _media_id_candidates(job):
        stem = re.sub(rf"\s*\[{re.escape(media_id)}\]", "", stem)
    stem = re.sub(r"\s*\[(best|1080|720|480|360)\]$", "", stem, flags=re.IGNORECASE).strip()
    stem = stem or "video"
    return _unique_path(file_path.with_name(f"{stem} [{quality}]{file_path.suffix}"))


def _rename_for_user_output(job: dict[str, Any], file_path: Path) -> Path:
    target = _user_output_path(job, file_path)
    if file_path.resolve() == target.resolve():
        return file_path
    os.replace(file_path, target)
    job["file_path"] = str(target)
    _job_log(job, "final-rename", f"from={file_path.name} to={target.name}")
    return target


def _ffmpeg_video_args_for_quality(quality: str) -> list[str]:
    args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    max_height = QUALITY_MAX_HEIGHTS.get(str(quality))
    if max_height:
        args.extend(["-vf", f"scale=-2:min(ih\\,{max_height}),setsar=1"])
    return args


async def _probe_media(file_path: Path) -> dict[str, Any] | None:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path or not file_path.exists():
        return None

    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,pix_fmt,width,height",
        "-show_entries",
        "format=duration,size,format_name",
        "-of",
        "json",
        str(file_path),
    ]
    return_code, output = await _run_command(cmd, timeout=30)
    if return_code != 0:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _media_duration(probe: dict[str, Any] | None) -> float:
    if not probe:
        return 0.0
    try:
        return max(0.0, float(probe.get("format", {}).get("duration") or 0))
    except (TypeError, ValueError):
        return 0.0


def _stream_for(probe: dict[str, Any] | None, codec_type: str) -> dict[str, Any] | None:
    if not probe:
        return None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def _is_mp4_container(probe: dict[str, Any] | None) -> bool:
    format_name = str((probe or {}).get("format", {}).get("format_name") or "")
    return "mp4" in format_name or "mov" in format_name


def _needs_h264_transcode(probe: dict[str, Any] | None, quality: str) -> bool:
    video = _stream_for(probe, "video")
    if not video:
        return True

    codec = str(video.get("codec_name") or "").lower()
    pix_fmt = str(video.get("pix_fmt") or "").lower()
    if codec not in {"h264", "avc1"}:
        return True
    if pix_fmt and pix_fmt not in {"yuv420p", "yuvj420p"}:
        return True

    max_height = QUALITY_MAX_HEIGHTS.get(str(quality))
    if max_height:
        try:
            if int(video.get("height") or 0) > max_height:
                return True
        except (TypeError, ValueError):
            return True

    audio = _stream_for(probe, "audio")
    if audio and str(audio.get("codec_name") or "").lower() not in {"aac", "mp4a"}:
        return True

    return False


def _update_convert_progress(job: dict[str, Any], line: str, duration: float) -> None:
    match = FFMPEG_TIME_RE.match(line)
    if not match or duration <= 0:
        return
    out_seconds = int(match.group("time_ms")) / 1_000_000
    percent = max(0.0, min(99.0, (out_seconds / duration) * 100))
    job["progress"] = round(percent, 1)
    job["message"] = f"Dang convert MP4 H.264 ({job['progress']}%)"
    _job_log_progress(job, "convert-progress", f"{job['progress']:.1f}% duration={duration:.1f}s", job["progress"])


def _find_downloaded_file(job: dict[str, Any], output_dir: Path, started_at: float) -> Path | None:
    file_path = str(job.get("file_path") or "").strip().strip('"')
    if file_path:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = output_dir / candidate
        if candidate.exists() and candidate.suffix.lower() in VIDEO_FILE_EXTENSIONS:
            return candidate

    for media_id in _media_id_candidates(job):
        marker = f"[{media_id}]"
        for candidate in output_dir.glob("*"):
            if (
                candidate.is_file()
                and marker in candidate.name
                and candidate.suffix.lower() in VIDEO_FILE_EXTENSIONS
                and not candidate.name.endswith(".part")
                and ".compatible.tmp" not in candidate.name
            ):
                return candidate

    candidates = [
        item
        for item in output_dir.glob("*")
        if item.is_file()
        and item.suffix.lower() in VIDEO_FILE_EXTENSIONS
        and item.stat().st_mtime >= started_at - 5
        and not item.name.endswith(".part")
        and ".compatible.tmp" not in item.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _media_id_candidates(job: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for raw_url in (job.get("url"), job.get("original_url")):
        url = str(raw_url or "")
        if not url:
            continue
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        youtube_id = (query.get("v") or [""])[0]
        if youtube_id:
            ids.append(youtube_id)

        host = parsed.netloc.lower()
        path_parts = [part for part in parsed.path.split("/") if part]
        if "youtu.be" in host and path_parts:
            ids.append(path_parts[0])
        for part in reversed(path_parts):
            if re.fullmatch(r"\d{8,}", part) or re.fullmatch(r"[a-zA-Z0-9_-]{8,}", part):
                ids.append(part)
                break

    seen: set[str] = set()
    return [item for item in ids if item and not (item in seen or seen.add(item))]


def _app_profile_cookie_arg() -> str:
    return f"chrome:{CHROME_PROFILE_DIR}"


def _platform_from_url(url: str, fallback: str = "other") -> str:
    lowered = url.lower()
    parsed = urlparse(url)
    suffix = Path(parsed.path.lower()).suffix
    if suffix in DIRECT_MEDIA_EXTENSIONS:
        return "direct"
    if "drive.google.com" in lowered or "drive.usercontent.google.com" in lowered:
        return "google_drive"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "tiktok.com" in lowered:
        return "tiktok"
    if "facebook.com" in lowered or "fb.watch" in lowered:
        return "facebook"
    return fallback


def _is_tiktok_photo_url(url: str) -> bool:
    parsed = urlparse(url)
    return "tiktok.com" in parsed.netloc.lower() and "/photo/" in parsed.path.lower()


def _is_facebook_story_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return ("facebook.com" in host or "fb.watch" in host) and "/stories/" in parsed.path.lower()


def _normalize_download_url(url: str) -> str:
    parsed = urlparse(url)
    lowered_host = parsed.netloc.lower()
    lowered_path = parsed.path.lower()
    if "tiktok.com" in lowered_host and "/video/" in lowered_path:
        return parsed._replace(query="", fragment="").geturl()
    return url


def _google_drive_file_id(url: str) -> str:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id", [""])[0]
    if query_id:
        return query_id
    match = re.search(r"/file/d/([^/]+)", parsed.path)
    return match.group(1) if match else ""


def _google_drive_alternate_urls(url: str) -> list[str]:
    file_id = _google_drive_file_id(url)
    if not file_id:
        return []
    return [
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download",
    ]


def _url_support_info(url: str, fallback: str = "other") -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        return {
            "supported": False,
            "source": "invalid",
            "message": "Link không hợp lệ. Hãy dán link bắt đầu bằng http:// hoặc https://.",
        }

    source = _platform_from_url(url, fallback)
    if source == "tiktok" and _is_tiktok_photo_url(url):
        return {
            "supported": False,
            "source": source,
            "message": "Link này là TikTok photo/slideshow. Hiện tool chỉ hỗ trợ TikTok video dạng /video/<id>. Hãy gửi link video TikTok, không phải link photo.",
        }
    if source == "facebook" and _is_facebook_story_url(url):
        return {
            "supported": False,
            "source": source,
            "message": "Link nay la Facebook Story. Hien tool chi ho tro Facebook video/reel/watch public; Story chua ho tro. Hay gui link video, reel hoac watch thay vi story.",
        }
    if source == "direct":
        suffix = Path(urlparse(url).path.lower()).suffix
        return {
            "supported": True,
            "source": source,
            "message": f"Đã nhận diện link file trực tiếp {suffix}. Có thể tải bằng chế độ Link file.",
        }
    if source == "google_drive":
        file_id = _google_drive_file_id(url)
        return {
            "supported": bool(file_id),
            "source": source,
            "message": (
                "Đã nhận diện Google Drive. File public tải trực tiếp được; file riêng tư cần đăng nhập Drive trong Chrome profile."
                if file_id
                else "Link Google Drive chưa đúng dạng chia sẻ file. Hãy dùng link có /file/d/<id> hoặc ?id=<id>."
            ),
        }
    if source in {"youtube", "tiktok", "facebook"}:
        normalized_url = _normalize_download_url(url)
        return {
            "supported": True,
            "source": source,
            "normalized_url": normalized_url,
            "message": "Đã nhận diện nền tảng hỗ trợ. Nếu bị hỏi đăng nhập, dùng Chrome profile riêng.",
        }
    return {
        "supported": False,
        "source": source,
        "message": "Nền tảng này chưa hỗ trợ trong UI hiện tại. Hãy dùng YouTube, TikTok, Facebook, Google Drive hoặc link .mp4/.m3u8/.mpd.",
    }


def _facebook_alternate_urls(url: str) -> list[str]:
    reel_match = re.search(r"facebook\.com/(?:reel|watch)/(?P<id>\d+)", url)
    query_match = re.search(r"[?&]v=(?P<id>\d+)", url)
    video_id = (reel_match or query_match).group("id") if (reel_match or query_match) else ""
    if not video_id:
        return []
    return [
        f"https://m.facebook.com/watch/?v={video_id}",
        f"https://mbasic.facebook.com/watch/?v={video_id}",
    ]


async def _run_command(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(ROOT),
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        output, _ = await process.communicate()
        return 124, _decode_process_output(output)
    return process.returncode or 0, _decode_process_output(output)


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"process", "task", "log_lines"} and not key.startswith("_")
    } | {"log_tail": job.get("log_lines", [])[-12:]}


def _job_file_path(job: dict[str, Any]) -> Path | None:
    file_path = str(job.get("file_path") or "").strip().strip('"')
    if not file_path:
        return None
    path = Path(file_path)
    if path.exists() and path.is_file():
        return path
    return None


def _cleanup_processing_files() -> int:
    output_dir = _safe_output_dir()
    cutoff = time.time() - PROCESSING_RETENTION_SECONDS
    removed = 0
    for item in output_dir.glob("*"):
        if not item.is_file():
            continue
        if item.suffix.lower() not in VIDEO_FILE_EXTENSIONS and ".tmp." not in item.name:
            continue
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink()
                removed += 1
        except OSError:
            continue
    return removed


async def _processing_cleanup_loop(_: web.Application) -> None:
    while True:
        removed = await asyncio.to_thread(_cleanup_processing_files)
        if removed:
            _job_log(None, "cleanup", f"removed={removed} retention={PROCESSING_RETENTION_SECONDS}s")
        await asyncio.sleep(60 * 60)


async def _start_background_tasks(app: web.Application) -> None:
    output_dir = _safe_output_dir()
    _job_log(None, "backend-start", f"host={APP_HOST} port={APP_PORT} processing_dir={output_dir}")
    app["processing_cleanup_task"] = asyncio.create_task(_processing_cleanup_loop(app))


async def _cleanup_background_tasks(app: web.Application) -> None:
    task = app.get("processing_cleanup_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _auth_args(job: dict[str, Any]) -> list[str]:
    args: list[str] = []
    if job.get("source") == "direct" and not job.get("cookies_file") and not job.get("use_browser_cookies"):
        return args

    if job.get("use_app_profile"):
        args.extend(["--cookies-from-browser", _app_profile_cookie_arg()])
    elif job.get("use_browser_cookies"):
        args.extend(["--cookies-from-browser", "chrome"])
    elif job.get("cookies_file"):
        args.extend(["--cookies", job["cookies_file"]])

    if args:
        args.extend(["--js-runtimes", "node", "--remote-components", "ejs:github"])
    return args


def _common_download_args(job: dict[str, Any], output_dir: Path, url: str | None = None) -> list[str]:
    output_template = f"%(title).180B [%(id)s] [{_quality_filename_suffix(job.get('quality'))}].%(ext)s"
    return [
        "--newline",
        "--no-warnings",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "--concurrent-fragments",
        "4",
        *_auth_args(job),
        *_format_for_quality(job["quality"]),
        "-P",
        str(output_dir),
        "-o",
        output_template,
        url or job["url"],
    ]


def _download_strategies(job: dict[str, Any], output_dir: Path) -> list[tuple[str, list[str]]]:
    base_args = _common_download_args(job, output_dir)
    if job.get("source") == "direct":
        return [
            ("direct-media", base_args),
            (
                "direct-media-browser-headers",
                [
                    "--user-agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                    "--referer",
                    job["url"],
                    *base_args,
                ],
            ),
        ]

    if job.get("source") == "google_drive":
        strategies = [("google-drive", base_args)]
        for alt_url in _google_drive_alternate_urls(job["url"]):
            strategies.append((f"google-drive-alt-{len(strategies)}", _common_download_args(job, output_dir, alt_url)))
        return strategies

    if job.get("source") != "tiktok":
        if job.get("source") != "facebook":
            return [("default", base_args)]

        strategies: list[tuple[str, list[str]]] = [
            ("facebook-web", base_args),
            (
                "facebook-mobile-headers",
                [
                    "--user-agent",
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
                    "--referer",
                    "https://m.facebook.com/",
                    *base_args,
                ],
            ),
        ]
        for alt_url in _facebook_alternate_urls(job["url"]):
            strategies.append((f"facebook-alt-{len(strategies)}", _common_download_args(job, output_dir, alt_url)))
            strategies.append(
                (
                    f"facebook-alt-mobile-{len(strategies)}",
                    [
                        "--user-agent",
                        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
                        "--referer",
                        "https://m.facebook.com/",
                        *_common_download_args(job, output_dir, alt_url),
                    ],
                )
            )
        return strategies

    return [
        ("tiktok-web", base_args),
        (
            "tiktok-web-headers",
            [
                "--user-agent",
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
                "--referer",
                "https://www.tiktok.com/",
                *base_args,
            ],
        ),
        (
            "tiktok-mobile-api-useast",
            [
                "--extractor-args",
                "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com",
                *base_args,
            ],
        ),
        (
            "tiktok-mobile-api-trill",
            [
                "--extractor-args",
                "tiktok:app_name=trill;aid=1180;api_hostname=api16-normal-c-alisg.tiktokv.com",
                *base_args,
            ],
        ),
    ]


def _update_from_line(job: dict[str, Any], line: str) -> None:
    clean = line.strip()
    if not clean:
        return

    job.setdefault("log_lines", []).append(clean)
    job["message"] = clean

    if "ERROR:" in clean or clean.lower().startswith("error"):
        job["error_message"] = clean
        _job_log(job, "tool-error", clean[-600:], level="ERROR")

    if "Destination:" in clean:
        job["file_path"] = clean.split("Destination:", 1)[1].strip()
        _job_log(job, "file-detected", f"destination={job['file_path']}")
    elif "Merging formats into" in clean:
        match = re.search(r'Merging formats into "(.+)"', clean)
        if match:
            job["file_path"] = match.group(1)
            _job_log(job, "merge-output", f"file={job['file_path']}")
    elif "has already been downloaded" in clean:
        match = re.search(r"\[download\]\s+(.+?)\s+has already been downloaded", clean)
        if match:
            job["file_path"] = match.group(1).strip()
            _job_log(job, "file-existing", f"file={job['file_path']}")
    elif clean.startswith("[ExtractAudio] Destination:"):
        job["file_path"] = clean.split("Destination:", 1)[1].strip()
        _job_log(job, "file-detected", f"audio_destination={job['file_path']}")

    progress = PROGRESS_RE.search(clean)
    if progress:
        job["progress"] = float(progress.group("percent"))
        if progress.group("size"):
            job["size"] = progress.group("size")
        if progress.group("speed"):
            job["speed"] = progress.group("speed")
        _job_log_progress(
            job,
            "download-progress",
            f"{job['progress']:.1f}% size={job.get('size') or '-'} speed={job.get('speed') or '-'}",
            job["progress"],
        )


async def _convert_to_compatible_mp4_legacy(job: dict[str, Any], output_dir: Path, started_at: float) -> bool:
    source_path = _find_downloaded_file(job, output_dir, started_at)
    if not source_path:
        job["message"] = "Tải xong nhưng chưa xác định được file để convert MP4."
        return False

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        job["file_path"] = str(source_path)
        job["message"] = "Tải xong nhưng thiếu ffmpeg để convert MP4 H.264."
        return False

    final_path = source_path if source_path.suffix.lower() == ".mp4" else source_path.with_suffix(".mp4")
    temp_path = final_path.with_name(f"{final_path.stem}.compatible.tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    quality = str(job.get("quality") or "best")
    quality_label = "best" if quality == "best" else f"{quality}p"
    job["status"] = "converting"
    job["message"] = f"Đang convert MP4 H.264 {quality_label} để Windows mở được"
    job["progress"] = max(float(job.get("progress") or 0), 99)
    job["file_path"] = str(final_path)
    _update_from_line(job, f"[tool] Converting to compatible MP4: {final_path.name}")

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        *_ffmpeg_video_args_for_quality(quality),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(temp_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(ROOT),
    )
    job["process"] = process

    assert process.stdout is not None
    async for raw_line in process.stdout:
        clean = _decode_process_output(raw_line).strip()
        if clean:
            job.setdefault("log_lines", []).append(clean)

    return_code = await process.wait()
    if job.get("status") == "cancelled":
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    if return_code != 0 or not temp_path.exists():
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        job["message"] = f"Tải xong nhưng convert MP4 thất bại (ffmpeg exit {return_code})."
        job["return_code"] = return_code
        job["file_path"] = str(source_path)
        return False

    try:
        if source_path.resolve() != final_path.resolve() and source_path.exists():
            source_path.unlink()
        os.replace(temp_path, final_path)
    except OSError as exc:
        job["message"] = f"Convert xong nhưng không thay được file MP4: {exc}"
        job["file_path"] = str(temp_path)
        return False

    job["file_path"] = str(final_path)
    job["message"] = "Tải hoàn tất - MP4 H.264 tương thích Windows"
    await _optimize_mp4_with_bento4(job, final_path)
    return True


async def _convert_to_compatible_mp4_v2(job: dict[str, Any], output_dir: Path, started_at: float) -> bool:
    source_path = _find_downloaded_file(job, output_dir, started_at)
    if not source_path:
        job["message"] = "Tai xong nhung chua xac dinh duoc file de convert MP4."
        _job_log(job, "convert-missing-file", job["message"], level="ERROR")
        return False

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        job["file_path"] = str(source_path)
        job["message"] = "Tai xong nhung thieu ffmpeg de convert MP4 H.264."
        _job_log(job, "convert-missing-ffmpeg", job["message"], level="ERROR")
        return False

    final_path = source_path if source_path.suffix.lower() == ".mp4" else source_path.with_suffix(".mp4")
    temp_path = final_path.with_name(f"{final_path.stem}.compatible.tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    quality = str(job.get("quality") or "best")
    probe = await _probe_media(source_path)
    duration = _media_duration(probe)
    video_stream = _stream_for(probe, "video") or {}
    audio_stream = _stream_for(probe, "audio") or {}
    _job_log(
        job,
        "probe",
        (
            f"file={source_path.name} vcodec={video_stream.get('codec_name') or '-'} "
            f"height={video_stream.get('height') or '-'} acodec={audio_stream.get('codec_name') or '-'} "
            f"duration={duration:.1f}s"
        ),
    )

    if not _needs_h264_transcode(probe, quality):
        job["file_path"] = str(final_path)
        if source_path.resolve() != final_path.resolve() or not _is_mp4_container(probe):
            job["status"] = "optimizing"
            job["message"] = "Dang dong goi lai MP4 tuong thich"
            job["progress"] = 99
            _job_log(job, "remux-start", f"file={final_path.name}")
            process = await asyncio.create_subprocess_exec(
                ffmpeg_path,
                "-y",
                "-i",
                str(source_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(ROOT),
            )
            job["process"] = process
            output, _ = await process.communicate()
            if output:
                job.setdefault("log_lines", []).extend(_decode_process_output(output).splitlines()[-12:])
            if job.get("status") == "cancelled":
                temp_path.unlink(missing_ok=True)
                _job_log(job, "remux-cancelled", f"file={final_path.name}", level="WARN")
                return False
            if process.returncode != 0 or not temp_path.exists() or temp_path.stat().st_size == 0:
                temp_path.unlink(missing_ok=True)
                job["message"] = f"Tai xong nhung remux MP4 that bai (ffmpeg exit {process.returncode})."
                job["return_code"] = process.returncode
                job["file_path"] = str(source_path)
                _job_log(job, "remux-failed", job["message"], level="ERROR")
                return False
            if source_path.resolve() != final_path.resolve() and source_path.exists():
                source_path.unlink()
            os.replace(temp_path, final_path)

        job["file_path"] = str(final_path)
        job["message"] = "Tai hoan tat - MP4 H.264/AAC tuong thich Windows"
        _job_log(job, "remux-completed", f"file={final_path.name}")
        await _optimize_mp4_with_bento4(job, final_path)
        _rename_for_user_output(job, Path(job["file_path"]))
        return True

    quality_label = "best" if quality == "best" else f"{quality}p"
    job["status"] = "converting"
    job["message"] = f"Dang convert MP4 H.264 {quality_label} de Windows mo duoc"
    job["progress"] = 0
    job["file_path"] = str(final_path)
    _job_log(job, "convert-start", f"quality={quality_label} input={source_path.name} output={final_path.name}")

    process = await asyncio.create_subprocess_exec(
        ffmpeg_path,
        "-y",
        "-nostats",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        *_ffmpeg_video_args_for_quality(quality),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(temp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(ROOT),
    )
    job["process"] = process

    assert process.stdout is not None
    async for raw_line in process.stdout:
        clean = _decode_process_output(raw_line).strip()
        if clean:
            job.setdefault("log_lines", []).append(clean)
            _update_convert_progress(job, clean, duration)

    return_code = await process.wait()
    if job.get("status") == "cancelled":
        temp_path.unlink(missing_ok=True)
        _job_log(job, "convert-cancelled", f"file={final_path.name}", level="WARN")
        return False
    if return_code != 0 or not temp_path.exists() or temp_path.stat().st_size == 0:
        temp_path.unlink(missing_ok=True)
        job["message"] = f"Tai xong nhung convert MP4 that bai (ffmpeg exit {return_code})."
        job["return_code"] = return_code
        job["file_path"] = str(source_path)
        _job_log(job, "convert-failed", job["message"], level="ERROR")
        return False

    try:
        if source_path.resolve() != final_path.resolve() and source_path.exists():
            source_path.unlink()
        os.replace(temp_path, final_path)
    except OSError as exc:
        job["message"] = f"Convert xong nhung khong thay duoc file MP4: {exc}"
        job["file_path"] = str(temp_path)
        _job_log(job, "convert-replace-failed", job["message"], level="ERROR")
        return False

    job["file_path"] = str(final_path)
    job["message"] = "Tai hoan tat - MP4 H.264 tuong thich Windows"
    _job_log(job, "convert-completed", f"file={final_path.name}")
    await _optimize_mp4_with_bento4(job, final_path)
    _rename_for_user_output(job, Path(job["file_path"]))
    return True


async def _optimize_mp4_with_bento4(job: dict[str, Any], file_path: Path) -> None:
    mp4compact = _bento4_tool("mp4compact")
    if not mp4compact or not file_path.exists() or file_path.suffix.lower() != ".mp4":
        return

    temp_path = file_path.with_name(f"{file_path.stem}.bento4.tmp.mp4")
    try:
        if temp_path.exists():
            temp_path.unlink()

        job["status"] = "optimizing"
        job["message"] = "Đang tối ưu MP4 bằng Bento4"
        _job_log(job, "optimize-start", f"tool=mp4compact file={file_path.name}")
        process = await asyncio.create_subprocess_exec(
            mp4compact,
            str(file_path),
            str(temp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        output, _ = await process.communicate()
        if job.get("status") == "cancelled":
            temp_path.unlink(missing_ok=True)
            _job_log(job, "optimize-cancelled", f"file={file_path.name}", level="WARN")
            return
        if output:
            job.setdefault("log_lines", []).extend(_decode_process_output(output).splitlines()[-8:])
        if process.returncode == 0 and temp_path.exists() and temp_path.stat().st_size > 0:
            os.replace(temp_path, file_path)
            job["message"] = "Tải hoàn tất - MP4 H.264 đã tối ưu"
            _job_log(job, "optimize-completed", f"file={file_path.name}")
        else:
            temp_path.unlink(missing_ok=True)
            job["message"] = "Tải hoàn tất - MP4 H.264 tương thích Windows"
            _job_log(job, "optimize-skipped", f"mp4compact_exit={process.returncode} file={file_path.name}", level="WARN")
    except OSError as exc:
        _job_log(job, "optimize-error", f"Bento4 skipped: {exc}", level="WARN")
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        job["message"] = "Tải hoàn tất - MP4 H.264 tương thích Windows"


async def _download_worker(job_id: str) -> None:
    job = jobs[job_id]
    output_dir = Path(job["output_dir"])
    started_at = time.time()
    job["status"] = "downloading"
    _job_log(job, "worker-start", f"source={job.get('source')} quality={job.get('quality')} output_dir={output_dir}")

    return_code = 1
    for strategy_name, strategy_args in _download_strategies(job, output_dir):
        if job.get("status") == "cancelled":
            _job_log(job, "worker-cancelled-before-strategy", f"strategy={strategy_name}", level="WARN")
            break

        cmd = _yt_dlp_command() + strategy_args
        job["strategy"] = strategy_name
        job["command"] = " ".join(cmd)
        _job_log(job, "strategy-start", f"strategy={strategy_name}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        job["process"] = process

        assert process.stdout is not None
        async for raw_line in process.stdout:
            _update_from_line(job, _decode_process_output(raw_line))

        return_code = await process.wait()
        job["return_code"] = return_code
        if return_code == 0:
            _job_log(job, "strategy-success", f"strategy={strategy_name} exit=0")
            break

        _job_log(job, "strategy-failed", f"strategy={strategy_name} exit={return_code}", level="WARN")
        _update_from_line(job, f"[tool] Strategy failed: {strategy_name} (exit {return_code})")

    if job.get("status") == "cancelled":
        job["progress"] = job.get("progress", 0)
        _job_log(job, "job-cancelled", f"progress={job.get('progress', 0)}", level="WARN")
    elif return_code == 0:
        converted = await _convert_to_compatible_mp4_v2(job, output_dir, started_at)
        if job.get("status") == "cancelled":
            job["progress"] = job.get("progress", 0)
            _job_log(job, "job-cancelled", f"progress={job.get('progress', 0)}", level="WARN")
        elif converted:
            job["status"] = "completed"
            job["progress"] = 100
            job["return_code"] = 0
            _job_log(job, "job-completed", f"file={job.get('file_path')}")
        else:
            job["status"] = "failed"
            job["progress"] = 100
            _job_log(job, "job-failed", job.get("message") or "convert failed", level="ERROR")
    else:
        job["status"] = "failed"
        if job.get("error_message"):
            job["message"] = job["error_message"]
        elif job.get("source") == "google_drive":
            job["message"] = (
                job.get("message")
                or "Google Drive không cho tải. Hãy kiểm tra file đã share công khai hoặc đăng nhập Drive trong Chrome profile riêng."
            )
        elif job.get("source") == "other":
            job["message"] = (
                job.get("message")
                or "Nền tảng này chưa hỗ trợ hoặc link không phải media trực tiếp."
            )
        else:
            job["message"] = job.get("message") or "yt-dlp failed"
        _job_log(job, "job-failed", job.get("message") or f"yt-dlp exit={return_code}", level="ERROR")

    if job.get("status") in {"completed", "failed", "cancelled"}:
        job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - started_at
        _job_log(job, "worker-finished", f"final_status={job.get('status')} elapsed={elapsed:.1f}s")


async def index(_: web.Request) -> web.FileResponse:
    response = web.FileResponse(STATIC_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


async def admin(_: web.Request) -> web.FileResponse:
    response = web.FileResponse(STATIC_DIR / "admin.html")
    response.headers["Cache-Control"] = "no-store"
    return response


async def static_file(request: web.Request) -> web.FileResponse:
    filename = request.match_info["filename"]
    response = web.FileResponse(STATIC_DIR / filename)
    response.headers["Cache-Control"] = "no-store"
    return response


async def list_jobs(request: web.Request) -> web.Response:
    client_id = _client_id_from_request(request)
    scope = request.query.get("scope", "device")
    visible_jobs = jobs.values()
    if scope != "all" and client_id:
        visible_jobs = [job for job in visible_jobs if job.get("client_id") == client_id]
    ordered = sorted(visible_jobs, key=lambda item: item["created_at"], reverse=True)
    return web.json_response({"jobs": [_public_job(job) for job in ordered]})


async def check_url(request: web.Request) -> web.Response:
    payload = await request.json()
    url = str(payload.get("url", "")).strip()
    source = str(payload.get("source") or "other").lower()
    info = _url_support_info(url, source)
    return web.json_response(info, status=200 if info["supported"] else 400)


async def create_job(request: web.Request) -> web.Response:
    payload = await request.json()
    url = str(payload.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return web.json_response({"success": False, "error": "Link video không hợp lệ"}, status=400)

    support_info = _url_support_info(url, payload.get("source", "auto"))
    if not support_info["supported"]:
        return web.json_response({"success": False, "error": support_info["message"], "check": support_info}, status=400)
    download_url = support_info.get("normalized_url") or _normalize_download_url(url)

    output_dir = _safe_output_dir()
    cookies_file = (payload.get("cookies_file") or "").strip()
    if cookies_file:
        cookies_path = Path(os.path.expanduser(cookies_file)).resolve()
        if not cookies_path.exists():
            return web.json_response(
                {"success": False, "error": f"Không tìm thấy cookies.txt: {cookies_path}"},
                status=400,
            )
        cookies_file = str(cookies_path)

    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id,
        "client_id": _client_id_from_request(request),
        "url": download_url,
        "original_url": url,
        "source": support_info["source"],
        "quality": payload.get("quality", "1080"),
        "audio_only": False,
        "allow_playlist": False,
        "use_app_profile": bool(payload.get("use_app_profile", True)),
        "use_browser_cookies": bool(payload.get("use_browser_cookies", False)),
        "cookies_file": cookies_file,
        "output_dir": str(output_dir),
        "status": "queued",
        "progress": 0,
        "size": "",
        "speed": "",
        "file_path": "",
        "message": "Đang chuẩn bị tải",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": "",
        "return_code": None,
        "log_lines": [],
    }
    jobs[job_id] = job
    _job_log(
        job,
        "job-created",
        f"client={job.get('client_id') or '-'} source={job['source']} quality={job['quality']} url={url}",
    )
    job["task"] = asyncio.create_task(_download_worker(job_id))
    return web.json_response({"success": True, "job": _public_job(job)})


async def open_platform_login(request: web.Request) -> web.Response:
    if not CHROME_EXE.exists():
        return web.json_response(
            {"success": False, "error": f"Không tìm thấy Chrome: {CHROME_EXE}"},
            status=404,
        )

    payload = await request.json()
    source = str(payload.get("source") or "youtube").lower()
    login_url = PLATFORM_LOGIN_URLS.get(source, PLATFORM_LOGIN_URLS["other"])
    CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(CHROME_EXE),
            f"--user-data-dir={CHROME_USER_DATA_DIR}",
            "--profile-directory=Default",
            login_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return web.json_response(
        {
            "success": True,
            "message": f"Đã mở Chrome profile riêng cho {source}. Đăng nhập, mở video xem vài giây, rồi đóng cửa sổ Chrome đó trước khi tải.",
            "source": source,
            "profile_dir": str(CHROME_PROFILE_DIR),
        }
    )


async def check_platform_login(request: web.Request) -> web.Response:
    payload = await request.json()
    source = str(payload.get("source") or "youtube").lower()
    url = str(payload.get("url") or "").strip()
    if not url and source == "youtube":
        url = YOUTUBE_TEST_URL
    if not url:
        return web.json_response(
            {"success": False, "error": "Dán một link video để kiểm tra đăng nhập nền tảng này."},
            status=400,
        )

    cmd = _yt_dlp_command()
    cmd.extend(
        [
            "--simulate",
            "--no-playlist",
            "--cookies-from-browser",
            _app_profile_cookie_arg(),
            "--js-runtimes",
            "node",
            "--remote-components",
            "ejs:github",
            "--print",
            "title",
            url,
        ]
    )
    return_code, output = await _run_command(cmd, timeout=90)
    return web.json_response(
        {
            "success": return_code == 0,
            "return_code": return_code,
            "source": _platform_from_url(url, source),
            "output": output[-4000:],
            "profile_dir": str(CHROME_PROFILE_DIR),
        },
        status=200 if return_code == 0 else 400,
    )


async def cancel_job(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    job = jobs.get(job_id)
    if not job:
        return web.json_response({"success": False, "error": "Không tìm thấy job"}, status=404)
    client_id = _client_id_from_request(request)
    if request.query.get("scope") != "all" and client_id and job.get("client_id") != client_id:
        return web.json_response({"success": False, "error": "Không tìm thấy job"}, status=404)

    if request.query.get("remove") == "1" and job.get("status") in {"completed", "failed", "cancelled"}:
        _job_log(job, "job-removed-from-list", f"client={client_id or '-'} status={job.get('status')}")
        jobs.pop(job_id, None)
        return web.json_response({"success": True, "removed": 1})

    process = job.get("process")
    if process and process.returncode is None:
        job["status"] = "cancelled"
        job["message"] = "Đã hủy"
        _job_log(job, "job-cancel-requested", f"client={client_id or '-'}", level="WARN")
        if os.name == "nt":
            process.terminate()
        else:
            os.kill(process.pid, signal.SIGTERM)
    return web.json_response({"success": True, "job": _public_job(job)})


async def clear_jobs(request: web.Request) -> web.Response:
    client_id = _client_id_from_request(request)
    removable = [
        job_id
        for job_id, job in jobs.items()
        if job["status"] in {"completed", "failed", "cancelled"}
        and (request.query.get("scope") == "all" or not client_id or job.get("client_id") == client_id)
    ]
    for job_id in removable:
        jobs.pop(job_id, None)
    return web.json_response({"success": True, "removed": len(removable)})


async def download_job_file(request: web.Request) -> web.StreamResponse:
    job = jobs.get(request.match_info["job_id"])
    if not job:
        return web.json_response({"success": False, "error": "Khong tim thay job"}, status=404)

    client_id = _client_id_from_request(request)
    if request.query.get("scope") != "all" and client_id and job.get("client_id") != client_id:
        return web.json_response({"success": False, "error": "Khong tim thay job"}, status=404)
    if job.get("status") != "completed":
        return web.json_response({"success": False, "error": "File chua san sang de tai ve"}, status=409)

    file_path = _job_file_path(job)
    if not file_path:
        _job_log(job, "client-pull-missing-file", f"client={client_id or '-'}", level="ERROR")
        return web.json_response({"success": False, "error": "Khong tim thay file tren server"}, status=404)

    _job_log(job, "client-pull-start", f"client={client_id or '-'} file={file_path.name} bytes={file_path.stat().st_size}")
    response = web.FileResponse(
        file_path,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_path.name)}",
            "Cache-Control": "no-store",
        },
    )
    return response


async def get_config(_: web.Request) -> web.Response:
    output_dir = _safe_output_dir()
    lan_ip = _lan_ip()
    public_host = lan_ip if APP_HOST in {"0.0.0.0", "::"} else APP_HOST
    return web.json_response(
        {
            "download_dir": str(output_dir),
            "host": APP_HOST,
            "port": APP_PORT,
            "local_url": f"http://127.0.0.1:{APP_PORT}",
            "public_url": f"http://{public_host}:{APP_PORT}",
            "token_required": bool(API_TOKEN),
            "allowed_origins": sorted(ALLOWED_ORIGINS),
            "qualities": [
                {"id": "best", "label": "Tốt nhất có thể"},
                {"id": "1080", "label": "1080p (Full HD)"},
                {"id": "720", "label": "720p (HD)"},
                {"id": "480", "label": "480p"},
                {"id": "360", "label": "360p"},
            ],
        }
    )


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "name": "VideoGet", "port": APP_PORT})


async def setup_status(_: web.Request) -> web.Response:
    yt_dlp_status, ffmpeg_status = await asyncio.gather(
        _tool_version(_yt_dlp_command() + ["--version"]),
        _tool_version(["ffmpeg", "-version"]),
    )

    platforms = {}
    for source, domains in PLATFORM_COOKIE_DOMAINS.items():
        cookie_count = _count_cookie_domains(domains)
        platforms[source] = {
            "ok": cookie_count > 0,
            "cookie_count": cookie_count,
            "message": (
                f"Đã thấy {cookie_count} cookie trong Chrome profile riêng."
                if cookie_count
                else "Chưa thấy cookie. Nếu nền tảng yêu cầu đăng nhập, hãy mở Chrome và đăng nhập trước."
            ),
        }

    chrome_ok = CHROME_EXE.exists()
    profile_ok = CHROME_PROFILE_DIR.exists()
    return web.json_response(
        {
            "python": {"ok": True, "version": sys.version.split()[0], "path": sys.executable},
            "yt_dlp": yt_dlp_status,
            "ffmpeg": ffmpeg_status,
            "chrome": {
                "ok": chrome_ok,
                "path": str(CHROME_EXE),
                "message": "Chrome OK" if chrome_ok else f"Không tìm thấy Chrome tại {CHROME_EXE}",
            },
            "profile": {
                "ok": profile_ok,
                "path": str(CHROME_PROFILE_DIR),
                "cookies_db": str(_chrome_cookies_db()),
                "message": "Profile riêng đã tồn tại" if profile_ok else "Chưa tạo profile riêng. Bấm Mở Chrome để tạo.",
            },
            "platforms": platforms,
        }
    )


@web.middleware
async def no_cache(request: web.Request, handler: Any) -> web.StreamResponse:
    response = await handler(request)
    if request.path == "/" or request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _is_allowed_origin(origin: str) -> bool:
    return "*" in ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS


def _apply_cors(request: web.Request, response: web.StreamResponse) -> web.StreamResponse:
    origin = request.headers.get("Origin", "")
    if origin and _is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = "*" if "*" in ALLOWED_ORIGINS else origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-VideoGet-Token, X-VideoGet-Client, Authorization, ngrok-skip-browser-warning"
        )
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response


def _request_token(request: web.Request) -> str:
    bearer = request.headers.get("Authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("X-VideoGet-Token", "").strip() or request.query.get("token", "").strip()


def _is_local_peer_request(request: web.Request) -> bool:
    peername = request.transport.get_extra_info("peername") if request.transport else None
    if not peername:
        return False

    peer_host = peername[0] if isinstance(peername, tuple) and peername else str(peername)
    try:
        return ipaddress.ip_address(peer_host).is_loopback
    except ValueError:
        return False


@web.middleware
async def api_security(request: web.Request, handler: Any) -> web.StreamResponse:
    if request.method == "OPTIONS":
        return _apply_cors(request, web.Response(status=204))

    if (
        request.path.startswith("/api/")
        and request.path != "/api/health"
        and API_TOKEN
        and not _is_local_peer_request(request)
    ):
        if _request_token(request) != API_TOKEN:
            return _apply_cors(
                request,
                web.json_response({"success": False, "error": "API token không hợp lệ"}, status=401),
            )

    response = await handler(request)
    return _apply_cors(request, response)


def create_app() -> web.Application:
    app = web.Application(middlewares=[api_security, no_cache])
    app.on_startup.append(_start_background_tasks)
    app.on_cleanup.append(_cleanup_background_tasks)
    app.router.add_get("/", index)
    app.router.add_get("/admin", admin)
    app.router.add_get("/admin.html", admin)
    app.router.add_get("/{filename:styles\\.css|app\\.js|client\\.js}", static_file)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/config", get_config)
    app.router.add_get("/api/setup/status", setup_status)
    app.router.add_post("/api/check-url", check_url)
    app.router.add_post("/api/auth/open", open_platform_login)
    app.router.add_post("/api/auth/check", check_platform_login)
    app.router.add_get("/api/jobs", list_jobs)
    app.router.add_post("/api/jobs", create_job)
    app.router.add_get("/api/jobs/{job_id}/file", download_job_file)
    app.router.add_delete("/api/jobs/completed", clear_jobs)
    app.router.add_delete("/api/jobs/{job_id}", cancel_job)
    app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=APP_HOST, port=APP_PORT)
