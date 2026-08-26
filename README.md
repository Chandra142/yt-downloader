# YT Downloader

A clean, responsive Flask web application for downloading media from YouTube and other supported platforms. Built for learning and portfolio purposes.

- **Backend:** Python 3.11+, Flask
- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Downloader:** yt-dlp with FFmpeg
- **Deployment:** Docker on Render

> **Responsible Use:** Only download content you own or have permission to download. Respect platform Terms of Service. This app does not bypass DRM, paywalls, or access controls.

## Quick Start

### Prerequisites
- **Python 3.11+**
- **FFmpeg** (required for MP4 merging, MP3 conversion, and subtitle embedding)

### Setup (Windows)
```cmd
# Clone and enter directory
cd yt-downloader

# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```
Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### Install FFmpeg (Windows)
1. Download from [ffmpeg.org](https://ffmpeg.org/download.html) → Windows → pre-built binary
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin` to your Windows `PATH` environment variable
4. Verify: `ffmpeg -version` in a new Command Prompt

> If FFmpeg is missing, the app will run but show warnings for failed conversions. Subtitles will not be embedded.

## Features

- Metadata preview (title, channel, duration, thumbnail)
- Multiple quality options (Best, 1080p, 720p, 480p, 360p)
- Download as MP4 or MP3
- **Subtitle embedding** — auto-fetches English captions (manual + auto-generated) and embeds them into MP4
- Real-time progress with speed & ETA
- **Paste button & drag-and-drop** — paste URLs from clipboard or drop them onto the input
- **Toast notifications** — animated feedback for actions and errors
- **Copy download link** — copy the direct file URL after download completes
- **Keyboard shortcuts** — Enter to fetch, Escape to cancel
- Dark/Light mode with localStorage persistence
- Fully responsive (desktop, tablet, mobile)
- Skeleton loading animations
- Security headers & path traversal protection
- Rate limiting & concurrent download limits
- Automatic cleanup of expired jobs

---

## Architecture

```
Browser → Flask App (app.py)
  ├── API Routes: /api/info, /api/download, /api/progress, /api/cancel
  ├── utils.py    — URL validation, sanitization, FFmpeg checks
  ├── config.py   — Environment variable configuration
  └── downloader.py — yt-dlp wrapper + in-memory job manager
        └─→ Background threads + yt-dlp + FFmpeg → downloads/
```

Downloads run in daemon threads. Job state stored in a module-level dict with `threading.Lock`.

---

## Project Structure

```
yt-downloader/
├── app.py                  # Flask API server
├── downloader.py           # Download logic & job manager
├── config.py               # Configuration
├── utils.py                # Helpers (validation, sanitization)
├── templates/              # HTML templates
│   ├── index.html
│   └── error.html
├── static/                 # CSS & JavaScript
│   ├── css/style.css
│   └── js/app.js
├── tests/                  # Unit & integration tests
│   ├── test_utils.py
│   └── test_routes.py
├── downloads/              # Temporary downloads (gitignored)
├── Dockerfile              # Production container
├── render.yaml             # Render deployment config
├── requirements.txt        # Dependencies
└── pytest.ini
```

## Development

### Run Tests
```bash
pytest -v
```
No environment setup required—`pytest.ini` handles imports automatically. Tests do not make real network requests.

### Run Locally
```bash
# Option 1: Direct Python
python app.py

# Option 2: Flask development server
flask --app app run --debug
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Production Server (Gunicorn)
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
```
Never use `debug=True` or `flask run` in production.

## Deployment (Render)

1. Push your code to GitHub
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and configures Docker build
5. (Optional) Add environment variables in dashboard
6. Click **Deploy**

**Note:** Render's free tier has an ephemeral filesystem. Files are temporary and lost on restart—by design.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-...` | Flask session secret (change in production) |
| `DOWNLOAD_DIR` | `downloads` | Temporary download directory |
| `MAX_CONCURRENT_DOWNLOADS` | `5` | Max simultaneous downloads |
| `JOB_EXPIRATION` | `3600` | Seconds before old jobs cleanup |
| `FLASK_ENV` | `development` | `production` or `development` |
| `MAX_REQUESTS_PER_MINUTE` | `10` | Rate limit per IP |

Copy `.env.example` to `.env` and edit as needed. Never commit `.env`.

## Security

- Backend URL validation (frontend not trusted)
- Format whitelist (only `best`, `audio_only`, and `height_*` accepted)
- Path traversal protection (`werkzeug.safe_join`)
- Server-side filename generation (no user input in paths)
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `CSP`)
- Per-IP rate limiting
- No shell injection (Python API, never `shell=True`)
- No secrets in responses (no stack traces or file paths leaked)

## Limitations

- **In-memory state** — job progress lost on server restart
- **Ephemeral storage** — files deleted on container restart (cloud platforms)
- **Single-process rate limiter** — doesn't work across multiple Gunicorn workers (use Nginx in production)
- **No persistence** — not designed as a file archive service
- **FFmpeg required** — needed for MP3 conversion, high-quality MP4 merging, and subtitle embedding

## Future Ideas

- Playlist support (batch downloads)
- Download queue with priority
- S3 storage for completed files (removes ephemeral limitation)
- Redis + Celery for distributed job queue
- User authentication & download history
- Server-Sent Events for progress (replace polling)
- Admin dashboard for monitoring

---

## License

[MIT License](LICENSE)