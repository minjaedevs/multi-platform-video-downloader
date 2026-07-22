# Deploy FE Public + Host API Local

## Có dùng được không?

Được, nhưng FE public không thể gọi `127.0.0.1` trên máy bạn. Bạn cần đưa API local ra một URL public bằng tunnel hoặc reverse proxy.

Mô hình:

```text
User browser -> FE public static site -> API public tunnel -> máy bạn chạy VideoGet
```

## 1. Chạy API local ở chế độ public test

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

Script sẽ in:

```text
API token: <token>
Local API: http://127.0.0.1:8787
LAN API: http://192.168.x.x:8787
```

Nếu dùng tunnel, trỏ tunnel tới:

```text
http://127.0.0.1:8787
```

Kết quả bạn sẽ có URL public kiểu:

```text
https://your-public-api-domain
```

## 2. Deploy FE

FE client là static files trong thư mục:

```text
docs
```

Nguồn FE nằm ở `web_static`. Khi sửa UI client, chạy:

```powershell
.\sync_pages_fe.cmd
```

Deploy các file này lên static hosting bất kỳ.

Khi gửi link cho user, thêm API URL và token:

```text
https://your-frontend-domain/?api=https://your-public-api-domain&token=<token>
```

FE sẽ lưu `api` và `token` vào localStorage, các lần sau có thể mở lại domain FE không cần query nữa.

## 3. CORS

Test nhanh:

```text
VIDEOGET_ALLOWED_ORIGINS=*
```

Khuyến nghị khi dùng domain thật:

```text
VIDEOGET_ALLOWED_ORIGINS=https://your-frontend-domain
```

## 4. Cảnh báo bảo mật

Không mở API này public lâu dài nếu chưa có auth mạnh hơn.

Rủi ro:

- Người khác có thể tạo job tải về máy host của bạn.
- File tải nằm trên máy host, không nằm trên máy user.
- Chrome profile có session đăng nhập nhạy cảm.
- Endpoint mở Chrome chỉ nên dùng khi chính bạn vận hành máy host.

Mức an toàn phù hợp: demo/test có kiểm soát, token đổi thường xuyên.
