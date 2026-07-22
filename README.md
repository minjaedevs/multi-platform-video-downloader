# VideoGet

VideoGet la web app tai video da nen tang. Client co the deploy len GitHub Pages, backend chay local tren may host va public tam thoi qua ngrok.

## Tinh Nang

- Tai video tu YouTube, TikTok, Facebook video/reel/watch public, Google Drive public, link file truc tiep `.mp4`, `.m3u8`, `.mpd`.
- Client cho user: dan link, chon nen tang, chon chat luong, chon folder tren may user va xem trang thai tai.
- Lich su tai tren client duoc tach theo tung thiet bi/browser.
- BE tai/convert trong folder xu ly tam; client pull file ve folder user da chon khi job hoan tat.
- Admin local: kiem tra Python, yt-dlp, ffmpeg, Chrome profile va hang doi.
- Dung Chrome profile rieng cho nen tang can dang nhap.
- Chat luong: `best`, `1080`, `720`, `480`, `360`.
- Sau khi tai xong, backend convert sang MP4 H.264 + AAC de Windows/phone mo duoc de hon.
- Neu user chon `1080`, `720`, `480`, `360`, buoc convert se gioi han dung height da chon. `best` giu do phan giai goc.
- Neu co Bento4 tai `D:\sports_data\Bento4\cmakebuild\Release`, backend se toi uu MP4 sau khi convert.
- File xu ly tam tren BE duoc giu 24h, cron nen trong app se tu don file cu.

## Cau Truc

```text
.
├── web_downloader_app.py      # Backend aiohttp API + download worker
├── web_static/                # UI local: client va admin
├── docs/                      # Client static cho GitHub Pages
├── tests/                     # Python tests
├── logs/                      # Log local, khong commit file .log
├── processing_storage/        # File BE xu ly tam, gitignored, auto clean sau 24h
├── chrome_profile/            # Chrome profile rieng, gitignored
├── .runtime/                  # Token/ngrok/runtime logs, gitignored
├── _dist/                     # Goi portable, gitignored
├── run_public_api_test.cmd    # Chay backend public mode local
├── run_ngrok_8787.cmd         # Public backend qua ngrok
├── print_demo_link.cmd        # In link demo FE + API + token
├── sync_pages_fe.cmd          # Sync web_static client sang docs
└── package_portable.cmd       # Dong goi zip gui may khac
```

## Cai Dat

```powershell
cd D:\be_video_downloader_mcp
.\install_dependencies.cmd
```

Can co:

- Python
- yt-dlp
- ffmpeg
- Google Chrome
- ngrok, neu muon share backend local ra ngoai
- Bento4 optional, de toi uu container MP4 sau convert

## Chay Local

Chay backend:

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

Mo admin local:

```text
http://127.0.0.1:8787/admin
```

Mo client local:

```text
http://127.0.0.1:8787/
```

## Log BE

BE ghi log ra console va file:

```text
D:\be_video_downloader_mcp\logs\video_jobs.log
```

Format moi:

```text
[job:<job_id> time:<YYYY-MM-DD HH:mm:ss> status:<status> level:<INFO|WARN|ERROR> event:<event>] <message>
```

Vi du:

```text
[job:a1b2c3d4e5 time:2026-07-22 14:30:05 status:downloading level:INFO event:download-progress] 50.1% size=120MiB speed=8.2MiB/s
[job:a1b2c3d4e5 time:2026-07-22 14:31:20 status:converting level:INFO event:convert-progress] 40.0% duration=320.0s
[job:a1b2c3d4e5 time:2026-07-22 14:33:02 status:completed level:INFO event:client-pull-start] client=abc file=video.mp4 bytes=123456789
```

Thu muc BE xu ly tam:

```text
D:\be_video_downloader_mcp\processing_storage
```

Folder luu tren may user duoc chon trong client bang nut `Chon`. Khi job hoan tat,
client se pull file tu BE ve folder do, roi xoa job khoi danh sach. Neu trinh
duyet khong ho tro chon folder truc tiep, user bam `Tai file` de tai ve theo
folder download cua trinh duyet.

Ten file output co kem chat luong user chon:

```text
Ten video [videoId] [best].mp4
Ten video [videoId] [720].mp4
Ten video [videoId] [360].mp4
```

## Cau Hinh Chrome Profile

Trong admin:

1. Mo `http://127.0.0.1:8787/admin`.
2. Chon nen tang YouTube/TikTok/Facebook/Drive.
3. Bam `Mo Chrome`.
4. Dang nhap trong cua so Chrome rieng.
5. Mo thu video vai giay.
6. Dong cua so Chrome do.
7. Quay lai admin va bam `Kiem tra`.

Chrome profile rieng nam tai:

```text
D:\be_video_downloader_mcp\chrome_profile\Default
```

Khong push/chia se thu muc `chrome_profile` vi co du lieu dang nhap.

## Public Backend Bang Ngrok

Terminal 1: chay backend:

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

Copy dong:

```text
API token: <API_TOKEN>
```

Terminal 2: chay ngrok:

```powershell
cd D:\be_video_downloader_mcp
.\run_ngrok_8787.cmd
```

Copy URL:

```text
https://xxxx.ngrok-free.dev
```

In link demo nhanh:

```powershell
.\print_demo_link.cmd
```

Link gui user co dang:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/?api=https://xxxx.ngrok-free.dev&token=<API_TOKEN>
```

## Deploy FE Len GitHub Pages

Khi sua client trong `web_static/`, sync sang `docs/`:

```powershell
.\sync_pages_fe.cmd
```

Commit va push:

```powershell
git add web_static docs
git commit -m "Update client"
git push origin main
```

Cau hinh GitHub Pages:

```text
Repo -> Settings -> Pages
Source: Deploy from a branch
Branch: main
Folder: /docs
Save
```

Client URL:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/
```

## Dong Goi Portable

```powershell
.\package_portable.cmd
```

Output:

```text
_dist\videoget-local.zip
```

Zip khong gom `.venv`, `.git`, `.runtime`, `chrome_profile`, log, cookies.

## API Chinh

```text
GET    /api/health
GET    /api/config
POST   /api/check-url
GET    /api/jobs
POST   /api/jobs
DELETE /api/jobs/completed
DELETE /api/jobs/{job_id}
POST   /api/auth/open
POST   /api/auth/check
GET    /api/setup/status
```

## Luu Y Production

Ngrok phu hop demo/test. Khi len VPS nen dung domain HTTPS that, reverse proxy Nginx/Caddy, token manh, process manager va thu muc download rieng.
