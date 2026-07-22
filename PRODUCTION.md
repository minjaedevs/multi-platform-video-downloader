# VideoGET Production Notes

## Run

```powershell
cd D:\be_video_downloader_mcp
.\run_web_downloader_prod.cmd
```

Open:

```text
http://127.0.0.1:8787
```

For LAN testing on another phone/PC in the same Wi-Fi:

```powershell
cd D:\be_video_downloader_mcp
.\run_web_downloader_lan.cmd
```

Send testers the `LAN:` URL printed by the script, for example:

```text
http://192.168.1.20:8787
```

## Configuration

Environment variables:

```text
VIDEOGET_HOST=127.0.0.1
VIDEOGET_PORT=8787
VIDEOGET_DOWNLOAD_DIR=C:\Users\Pc\video-downloader
VIDEOGET_CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe
VIDEOGET_CHROME_PROFILE_DIR=D:\be_video_downloader_mcp\chrome_profile
```

Keep `VIDEOGET_HOST=127.0.0.1` for local-only use. Do not expose this tool to
the public internet unless you add authentication and per-user download
isolation.

Use `VIDEOGET_HOST=0.0.0.0` only for local network testing. The downloaded files
are saved on the host machine, not on the tester's phone/PC.

## Platform Auth

The app uses a dedicated Chrome profile:

```text
D:\be_video_downloader_mcp\chrome_profile
```

Use the UI button `Mở Chrome đăng nhập` after selecting YouTube, TikTok, or
Facebook. Log in in that separate Chrome window, open the target video once,
then close that Chrome window before downloading.

This profile contains login session data. Do not commit, upload, or share it.

## Facebook

Facebook extraction is less stable when videos require login or when reels are
served through different web/mobile surfaces. The app retries:

```text
facebook-web
facebook-mobile-headers
facebook-alt m.facebook.com/watch/?v=...
facebook-alt mbasic.facebook.com/watch/?v=...
```

If a Facebook video only opens while logged in, use the Chrome profile login
flow first.

## TikTok

TikTok may fail intermittently because the page/API response changes by region,
cookie state, and account/session. The app retries web, mobile headers, and
mobile API host variants. Use the Chrome profile login flow when direct public
download fails.

## Maintenance

Keep yt-dlp fresh:

```powershell
C:\Users\Pc\AppData\Local\Python\bin\python.exe -m pip install --upgrade yt-dlp
```

If YouTube asks for bot verification, use either the Chrome profile flow or a
Netscape-format cookies.txt file.
