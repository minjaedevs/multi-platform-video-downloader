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
- Da bundle Bento4 `mp4compact.exe` tai `tools\bento4\bin` de toi uu container MP4 sau khi convert.
- File xu ly tam tren BE duoc giu 24h, cron nen trong app se tu don file cu.

## Cau Truc

```text
.
|-- web_downloader_app.py      # Backend aiohttp API + download worker
|-- web_static/                # UI local: client va admin
|-- docs/                      # Client static cho GitHub Pages
|-- tests/                     # Python tests
|-- logs/                      # Log local, khong commit file .log
|-- processing_storage/        # File BE xu ly tam, gitignored, auto clean sau 24h
|-- chrome_profile/            # Chrome profile rieng, gitignored
|-- tools/bento4/bin/          # Bento4 mp4compact bundled
|-- .env.mac.example           # Mau env cho macOS
|-- .runtime/                  # Token/ngrok/runtime logs, gitignored
|-- _dist/                     # Goi portable, gitignored
|-- run_public_api_test.cmd    # Chay backend public mode local
|-- run_ngrok_8787.cmd         # Public backend qua ngrok
|-- print_demo_link.cmd        # In link demo FE + API + token
|-- install_dependencies.sh    # Cai dependency Python tren macOS/Linux
|-- run_public_api_test.sh     # Chay backend public mode tren macOS/Linux
|-- run_ngrok_8787.sh          # Public backend qua ngrok tren macOS/Linux
|-- print_demo_link.sh         # In link demo FE + API + token tren macOS/Linux
|-- sync_pages_fe.cmd          # Sync web_static client sang docs
|-- sync_pages_fe.sh           # Sync web_static client sang docs tren macOS/Linux
`-- package_portable.cmd       # Dong goi zip gui may khac
```

## Cai Dat

```powershell
git clone https://github.com/minjaedevs/multi-platform-video-downloader.git
cd multi-platform-video-downloader
.\install_dependencies.cmd
```

macOS:

```bash
git clone https://github.com/minjaedevs/multi-platform-video-downloader.git
cd multi-platform-video-downloader
bash ./install_dependencies.sh
```

Neu repo da nam san tren may:

```powershell
cd D:\be_video_downloader_mcp
.\install_dependencies.cmd
```

Can co:

- Python
- yt-dlp, cai qua `requirements.txt`
- ffmpeg + ffprobe
- Google Chrome
- ngrok, neu muon share backend local ra ngoai
- Bento4: Windows da bundle `tools\bento4\bin\mp4compact.exe`; macOS can cai `bento4` qua Homebrew

## Cai Dependency Ngoai

`install_dependencies.cmd` tren Windows va `install_dependencies.sh` tren macOS chi cai Python package trong repo, gom `yt-dlp`, `aiohttp` va cac dependency trong `requirements.txt`. Cac tool ben duoi la chuong trinh he thong nen can cai rieng tren may host.

### Windows

Kiem tra Python:

```powershell
python --version
```

Neu lenh tren loi, cai Python 3.10+ roi tick `Add python.exe to PATH` khi cai. Sau do mo PowerShell moi va chay lai:

```powershell
python --version
python -m pip --version
```

`yt-dlp` duoc cai boi repo:

```powershell
cd D:\be_video_downloader_mcp
.\install_dependencies.cmd
```

Kiem tra:

```powershell
.\.venv\Scripts\python.exe -m yt_dlp --version
```

Neu may khong dung `.venv`, co the kiem tra bang:

```powershell
python -m yt_dlp --version
```

`ffmpeg` bat buoc de ghep audio/video, convert H.265/HEVC/AV1 sang MP4 H.264 + AAC va xu ly `.m3u8`.

Cai nhanh bang winget:

```powershell
winget install Gyan.FFmpeg
```

Dong PowerShell cu, mo PowerShell moi, kiem tra:

```powershell
ffmpeg -version
ffprobe -version
```

Neu van bao `ffmpeg is not recognized`, them thu muc `bin` cua ffmpeg vao `PATH`. Vi du:

```text
C:\ffmpeg\bin
```

Backend can ca `ffmpeg.exe` va `ffprobe.exe`.

Chrome can cho 2 viec:

- Admin mo Chrome profile rieng de login YouTube/TikTok/Facebook/Drive.
- Backend dung cookies cua profile rieng khi nen tang yeu cau dang nhap.

Kiem tra path mac dinh:

```powershell
Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Neu tra ve `False`, cai Google Chrome hoac cap nhat `.env`:

```env
VIDEOGET_CHROME_EXE=C:\Duong\Dan\Toi\chrome.exe
```

Sau khi chay backend, mo admin:

```text
http://127.0.0.1:8787/admin
```

Trong admin bam `Mo Chrome`, dang nhap tai nen tang can dung, mo thu video vai giay, dong Chrome, roi bam `Kiem tra`.

`ngrok` chi can khi muon public backend local ra ngoai cho user test qua GitHub Pages. Neu chi test local thi khong can ngrok.

Cai ngrok bang Microsoft Store hoac winget:

```powershell
winget install Ngrok.Ngrok
```

Mo PowerShell moi, kiem tra:

```powershell
ngrok version
```

Neu cai tu Microsoft Store ma lenh `ngrok` khong nhan, mo app ngrok mot lan tu Start Menu, hoac dung path:

```text
%LOCALAPPDATA%\Microsoft\WindowsApps\ngrok.exe
```

Cau hinh token:

```powershell
cd D:\be_video_downloader_mcp
.\configure_ngrok_token.cmd
```

Chay public backend:

```powershell
.\run_public_api_test.cmd
```

Mo terminal khac va public port `8787`:

```powershell
.\run_ngrok_8787.cmd
```

In link client demo:

```powershell
.\print_demo_link.cmd
```

### macOS

Tat ca dependency chinh deu support macOS. Khac biet lon nhat la script Windows `.cmd` khong chay truc tiep tren macOS, nen repo co them cac script `.sh` tuong duong.

Cai Homebrew neu may chua co:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Cai tool he thong:

```bash
brew install ffmpeg ngrok bento4
brew install --cask google-chrome
```

Kiem tra:

```bash
python3 --version
ffmpeg -version
ffprobe -version
ngrok version
mp4compact
test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" && echo "Chrome OK"
```

Cai Python package cua repo:

```bash
cd multi-platform-video-downloader
bash ./install_dependencies.sh
```

Neu muon chay script truc tiep khong can `bash`:

```bash
chmod +x *.sh
./install_dependencies.sh
```

Cau hinh ngrok token:

```bash
./configure_ngrok_token.sh
```

Chay backend local/public test:

```bash
./run_public_api_test.sh
```

Mo terminal khac va chay ngrok:

```bash
./run_ngrok_8787.sh
```

In link client demo:

```bash
./print_demo_link.sh
```

Admin local tren macOS:

```text
http://127.0.0.1:8787/admin
```

Chrome profile rieng tren macOS mac dinh nam trong repo:

```text
./chrome_profile/Default
```

Neu Chrome khong nam o path mac dinh, set bien moi truong truoc khi run:

```bash
export VIDEOGET_CHROME_EXE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

Ghi chu ve Bento4:

- Project chi dung tool `mp4compact` de toi uu container MP4 sau khi convert.
- Windows: repo da bundle `tools\bento4\bin\mp4compact.exe`.
- macOS: khong dung duoc file `.exe`, can `brew install bento4`; backend se tu tim `mp4compact` trong `PATH`.
- Neu muon dung Bento4 ban khac, set `VIDEOGET_BENTO4_BIN_DIR` trong `.env` hoac bien moi truong.
- Thong tin upstream/ban quyen Bento4 duoc luu tai `tools\bento4\README.Bento4.md`.

## Chay Local

Chay backend:

Windows:

```powershell
cd multi-platform-video-downloader
.\run_web_local.cmd
```

macOS:

```bash
cd multi-platform-video-downloader
bash ./run_web_local.sh
```

Neu dang lam tren folder hien tai:

```powershell
cd D:\be_video_downloader_mcp
.\run_web_local.cmd
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

Format:

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

Folder luu tren may user duoc chon trong client bang nut `Chon`. Khi job hoan tat, client se pull file tu BE ve folder do, roi xoa job khoi danh sach. Neu trinh duyet khong ho tro chon folder truc tiep, user bam `Tai file` de tai ve theo folder download cua trinh duyet.

Ten file output co kem chat luong user chon:

```text
Ten video [best].mp4
Ten video [720].mp4
Ten video [360].mp4
Ten video [720] (1).mp4
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

Windows:

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

macOS:

```bash
cd multi-platform-video-downloader
bash ./run_public_api_test.sh
```

Copy dong:

```text
API token: <API_TOKEN>
```

Terminal 2: chay ngrok:

Windows:

```powershell
cd D:\be_video_downloader_mcp
.\run_ngrok_8787.cmd
```

macOS:

```bash
cd multi-platform-video-downloader
bash ./run_ngrok_8787.sh
```

Copy URL:

```text
https://xxxx.ngrok-free.dev
```

In link demo nhanh:

Windows:

```powershell
.\print_demo_link.cmd
```

macOS:

```bash
bash ./print_demo_link.sh
```

Link gui user co dang:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/?api=https://xxxx.ngrok-free.dev&token=<API_TOKEN>
```

## Deploy FE Len GitHub Pages

Khi sua client trong `web_static/`, sync sang `docs/`:

Windows:

```powershell
.\sync_pages_fe.cmd
```

macOS:

```bash
bash ./sync_pages_fe.sh
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

Zip khong gom `.venv`, `.git`, `.runtime`, `chrome_profile`, log, cookies. Zip co gom `tools\bento4\bin\mp4compact.exe`.

## API Chinh

```text
GET    /api/health
GET    /api/config
POST   /api/check-url
GET    /api/jobs
POST   /api/jobs
GET    /api/jobs/{job_id}/file
DELETE /api/jobs/completed
DELETE /api/jobs/{job_id}
DELETE /api/jobs/{job_id}?remove=1
POST   /api/auth/open
POST   /api/auth/check
GET    /api/setup/status
```

## Luu Y Production

Ngrok phu hop demo/test. Khi len VPS nen dung domain HTTPS that, reverse proxy Nginx/Caddy, token manh, process manager va thu muc download rieng.
