# VideoGet Local Web

Local video downloader web UI + API powered by `yt-dlp`.

## Local Run

```powershell
cd D:\be_video_downloader_mcp
.\install_dependencies.cmd
.\run_web_downloader_prod.cmd
```

Open:

```text
http://127.0.0.1:8787
```

## Public Test With GitHub Pages + Ngrok

Run local API:

```powershell
cd D:\be_video_downloader_mcp
.\run_public_api_test.cmd
```

In another terminal:

```powershell
.\run_ngrok_8787.cmd
```

GitHub Pages client FE lives in:

```text
docs/
```

When client UI in `web_static` changes, sync FE:

```powershell
.\sync_pages_fe.cmd
```

GitHub Pages settings:

```text
Settings -> Pages -> Deploy from a branch -> main -> /docs
```

Open FE with API:

```text
https://<username>.github.io/<repo>/?api=https://<ngrok-domain>&token=<API_TOKEN>
```

`API_TOKEN` is printed by `run_public_api_test.cmd`.

## Security

Do not commit:

- `.env`
- `chrome_profile/`
- `*.log`
- `*cookies*.txt`
- `_dist/`

Ngrok URLs and demo tokens should be treated as temporary.
