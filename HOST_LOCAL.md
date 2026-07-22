# Host Local Cho User Test

## 1. Chạy riêng trên máy bạn

```powershell
cd D:\be_video_downloader_mcp
.\run_web_downloader.cmd
```

Mở:

```text
http://127.0.0.1:8787
```

## 2. Cho thiết bị khác cùng Wi-Fi test

```powershell
cd D:\be_video_downloader_mcp
.\run_web_downloader_lan.cmd
```

Copy dòng `LAN:` mà script in ra rồi gửi cho user test.

Nếu máy khác không mở được:

- Cho phép Python qua Windows Firewall ở mạng Private.
- Đảm bảo cùng Wi-Fi/LAN.
- Không dùng VPN chặn mạng nội bộ.

API health check:

```text
http://<LAN_IP>:8787/api/health
```

## 3. Đóng gói gửi máy khác

Tạo file zip:

```powershell
cd D:\be_video_downloader_mcp
.\package_portable.cmd
```

File tạo ra:

```text
D:\be_video_downloader_mcp\_dist\videoget-local.zip
```

Trên máy nhận:

```powershell
.\install_dependencies.cmd
.\run_web_downloader.cmd
```

Không gửi kèm thư mục `chrome_profile` vì có thể chứa phiên đăng nhập/cookies.
