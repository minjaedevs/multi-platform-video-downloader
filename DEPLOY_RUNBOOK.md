# VideoGet Deploy Runbook

Quy trình này dùng cho demo hiện tại:

```text
User -> GitHub Pages client -> ngrok public URL -> BE local trên máy host
Admin -> http://127.0.0.1:8787/admin
```

## 0. Thành phần

- `web_static/index.html` + `web_static/client.js`: trang client cho user.
- `web_static/admin.html` + `web_static/app.js`: trang admin local.
- `docs/`: bản client static để GitHub Pages deploy.
- `web_downloader_app.py`: BE API local.
- `chrome_profile/`: Chrome profile riêng, không push git.
- `ffmpeg`: dùng để merge audio/video chất lượng cao.
- `yt-dlp`: engine tải video.
- `ngrok`: public tunnel cho BE local.

## 1. Cài dependencies

```powershell
cd D:\be_video_downloader_mcp
.\install_dependencies.cmd
```

Kiểm tra local:

```powershell
cd D:\be_video_downloader_mcp
.\run_web_downloader_prod.cmd
```

Mở admin:

```text
http://127.0.0.1:8787/admin
```

Trong admin bấm `Kiểm tra`. Các mục nên OK:

- Python
- yt-dlp
- ffmpeg
- Chrome
- Profile

## 2. Cấu hình Chrome profile riêng

Mở:

```text
http://127.0.0.1:8787/admin
```

Thao tác:

1. Chọn nền tảng: YouTube, TikTok, Facebook hoặc Drive.
2. Mở `Tùy chọn đăng nhập`.
3. Bấm `Mở Chrome`.
4. Đăng nhập trong cửa sổ Chrome được mở ra.
5. Mở thử video vài giây.
6. Đóng cửa sổ Chrome đó.
7. Quay lại admin, bấm `Kiểm tra`.

Profile nằm tại:

```text
D:\be_video_downloader_mcp\chrome_profile\Default
```

Không push/thả thư mục này cho người khác.

## 3. Deploy FE lên GitHub Pages

Khi sửa client trong `web_static`, sync sang `docs`:

```powershell
cd D:\be_video_downloader_mcp
.\sync_pages_fe.cmd
```

Commit và push:

```powershell
git add web_static docs
git commit -m "Update client UI"
git push
```

GitHub Pages:

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

## 4. Chạy BE public test bằng ngrok

Terminal 1: chạy BE public API:

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

Copy dòng:

```text
API token: <API_TOKEN>
```

Terminal 2: chạy ngrok:

```powershell
cd D:\be_video_downloader_mcp
.\run_ngrok_8787.cmd
```

Copy dòng:

```text
Forwarding https://xxxx.ngrok-free.dev -> http://localhost:8787
```

Public API URL là:

```text
https://xxxx.ngrok-free.dev
```

## 5. Link gửi user

Ghép link:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/?api=https://xxxx.ngrok-free.dev&token=<API_TOKEN>
```

Nếu BE/ngrok do scripts của dự án chạy, có thể in link bằng:

```powershell
.\print_demo_link.cmd
```

User chỉ cần:

1. Mở link.
2. Dán video URL.
3. Chọn nền tảng.
4. Chọn chất lượng.
5. Bấm tải.

Admin local xử lý Chrome profile, yt-dlp, ffmpeg và hàng đợi.

## 6. Nếu đổi ngrok URL

Ngrok free thường đổi URL khi restart. Mỗi lần đổi URL:

1. Lấy URL ngrok mới.
2. Lấy API token từ terminal BE.
3. Gửi lại link client mới:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/?api=<NEW_NGROK_URL>&token=<API_TOKEN>
```

Nếu trình duyệt user bị lưu URL cũ, bảo họ mở link mới hoặc chạy:

```js
localStorage.clear()
location.reload()
```

## 7. Đóng gói gửi máy khác

```powershell
cd D:\be_video_downloader_mcp
.\package_portable.cmd
```

File zip:

```text
D:\be_video_downloader_mcp\_dist\videoget-local.zip
```

Zip không bao gồm:

- `.git`
- `.venv`
- `.runtime`
- `chrome_profile`
- `_dist`
- `.env`
- `*.log`
- `*cookies*.txt`

## 8. Chuẩn bị VPS sau này

Mô hình VPS:

```text
User -> GitHub Pages client -> HTTPS domain/VPS -> VideoGet BE -> yt-dlp/ffmpeg/Chrome profile
```

Env mẫu Linux:

```text
VIDEOGET_HOST=0.0.0.0
VIDEOGET_PORT=8787
VIDEOGET_DOWNLOAD_DIR=/data/videoget-processing
VIDEOGET_PROCESSING_RETENTION_SECONDS=86400
VIDEOGET_CHROME_EXE=/usr/bin/google-chrome
VIDEOGET_CHROME_PROFILE_DIR=/data/chrome_profile
VIDEOGET_ALLOWED_ORIGINS=https://minjaedevs.github.io
VIDEOGET_API_TOKEN=<strong-token>
```

Cần cài:

- Python
- yt-dlp
- ffmpeg
- Google Chrome hoặc Chromium
- reverse proxy HTTPS: Caddy hoặc Nginx
- process manager: systemd, pm2, supervisor hoặc Docker

Lưu ý VPS không có màn hình GUI mặc định. Phần login Chrome profile cần chuẩn bị riêng:

- remote desktop/VNC,
- hoặc xvfb,
- hoặc quy trình import profile/cookies an toàn.

## 9. Lệnh kiểm tra nhanh

Local health:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
```

Ngrok API config:

```powershell
$url = "https://xxxx.ngrok-free.dev"
$token = "<API_TOKEN>"
Invoke-RestMethod "$url/api/config" -Headers @{
  "X-VideoGet-Token" = $token
  "ngrok-skip-browser-warning" = "true"
}
```

Admin:

```text
http://127.0.0.1:8787/admin
```

Client:

```text
https://minjaedevs.github.io/multi-platform-video-downloader/?api=<NGROK_URL>&token=<API_TOKEN>
```
