#!/usr/bin/env python3
"""Local web UI for multi-platform video downloads."""

from __future__ import annotations

import asyncio
import json
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
from urllib.parse import parse_qs, urlparse

from aiohttp import web


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "web_static"
DEFAULT_DOWNLOAD_DIR = Path(os.environ.get("VIDEOGET_DOWNLOAD_DIR", Path.home() / "video-downloader"))
CHROME_EXE = Path(os.environ.get("VIDEOGET_CHROME_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
CHROME_USER_DATA_DIR = Path(os.environ.get("VIDEOGET_CHROME_PROFILE_DIR", ROOT / "chrome_profile"))
CHROME_PROFILE_DIR = CHROME_USER_DATA_DIR / "Default"
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

jobs: dict[str, dict[str, Any]] = {}

QUALITY_FORMATS = {
    "best": "bestvideo+bestaudio/best",
    "1080": "bestvideo*[height<=1080]+bestaudio/best[height<=1080]",
    "720": "bestvideo*[height<=720]+bestaudio/best[height<=720]",
    "480": "bestvideo*[height<=480]+bestaudio/best[height<=480]",
    "360": "bestvideo*[height<=360]+bestaudio/best[height<=360]",
}

PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%.*?(?:of\s+(?P<size>\S+))?.*?(?:at\s+(?P<speed>\S+))?",
    re.IGNORECASE,
)


def _yt_dlp_command() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


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
        return 124, output.decode("utf-8", errors="replace")
    return process.returncode or 0, output.decode("utf-8", errors="replace")


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"process", "task", "log_lines"}
    } | {"log_tail": job.get("log_lines", [])[-12:]}


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
    output_template = "%(title).180B [%(id)s].%(ext)s"
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

    if "Destination:" in clean:
        job["file_path"] = clean.split("Destination:", 1)[1].strip()
    elif "Merging formats into" in clean:
        match = re.search(r'Merging formats into "(.+)"', clean)
        if match:
            job["file_path"] = match.group(1)
    elif clean.startswith("[ExtractAudio] Destination:"):
        job["file_path"] = clean.split("Destination:", 1)[1].strip()

    progress = PROGRESS_RE.search(clean)
    if progress:
        job["progress"] = float(progress.group("percent"))
        if progress.group("size"):
            job["size"] = progress.group("size")
        if progress.group("speed"):
            job["speed"] = progress.group("speed")


async def _download_worker(job_id: str) -> None:
    job = jobs[job_id]
    output_dir = Path(job["output_dir"])
    job["status"] = "downloading"

    return_code = 1
    for strategy_name, strategy_args in _download_strategies(job, output_dir):
        if job.get("status") == "cancelled":
            break

        cmd = _yt_dlp_command() + strategy_args
        job["strategy"] = strategy_name
        job["command"] = " ".join(cmd)
        _update_from_line(job, f"[tool] Trying strategy: {strategy_name}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        job["process"] = process

        assert process.stdout is not None
        async for raw_line in process.stdout:
            _update_from_line(job, raw_line.decode("utf-8", errors="replace"))

        return_code = await process.wait()
        job["return_code"] = return_code
        if return_code == 0:
            break

        _update_from_line(job, f"[tool] Strategy failed: {strategy_name} (exit {return_code})")

    job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    if job.get("status") == "cancelled":
        job["progress"] = job.get("progress", 0)
    elif return_code == 0:
        job["status"] = "completed"
        job["progress"] = 100
        job["message"] = "Tải hoàn tất"
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


async def list_jobs(_: web.Request) -> web.Response:
    ordered = sorted(jobs.values(), key=lambda item: item["created_at"], reverse=True)
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

    output_dir = _safe_output_dir(payload.get("output_dir"))
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
    job = jobs.get(request.match_info["job_id"])
    if not job:
        return web.json_response({"success": False, "error": "Không tìm thấy job"}, status=404)

    process = job.get("process")
    if process and process.returncode is None:
        job["status"] = "cancelled"
        job["message"] = "Đã hủy"
        if os.name == "nt":
            process.terminate()
        else:
            os.kill(process.pid, signal.SIGTERM)
    return web.json_response({"success": True, "job": _public_job(job)})


async def clear_jobs(_: web.Request) -> web.Response:
    removable = [
        job_id
        for job_id, job in jobs.items()
        if job["status"] in {"completed", "failed", "cancelled"}
    ]
    for job_id in removable:
        jobs.pop(job_id, None)
    return web.json_response({"success": True, "removed": len(removable)})


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
            "Content-Type, X-VideoGet-Token, Authorization, ngrok-skip-browser-warning"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response


def _request_token(request: web.Request) -> str:
    bearer = request.headers.get("Authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("X-VideoGet-Token", "").strip()


@web.middleware
async def api_security(request: web.Request, handler: Any) -> web.StreamResponse:
    if request.method == "OPTIONS":
        return _apply_cors(request, web.Response(status=204))

    if request.path.startswith("/api/") and request.path != "/api/health" and API_TOKEN:
        if _request_token(request) != API_TOKEN:
            return _apply_cors(
                request,
                web.json_response({"success": False, "error": "API token không hợp lệ"}, status=401),
            )

    response = await handler(request)
    return _apply_cors(request, response)


def create_app() -> web.Application:
    app = web.Application(middlewares=[api_security, no_cache])
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
    app.router.add_delete("/api/jobs/completed", clear_jobs)
    app.router.add_delete("/api/jobs/{job_id}", cancel_job)
    app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=APP_HOST, port=APP_PORT)
