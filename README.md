# YT Downloader

> An educational web application for downloading media from supported URLs.  
> Built with Python, Flask, yt-dlp, and vanilla HTML/CSS/JavaScript.

---

## Overview

YT Downloader is a clean, responsive Flask web application that lets you
download media from YouTube and other supported platforms directly in your
browser. It is designed as a **portfolio and learning project** — the code is
intentionally simple enough to explain in a college viva/interview.

**Responsible Use:**  
Only download media you have explicit permission to download.  
Respect the Terms of Service of each platform.  
This application does **not** bypass DRM, paywalls, or access controls.

---

## Features

- Paste any supported URL and fetch video metadata (title, channel, duration, thumbnail)
- Select download quality (Best, 1080p, 720p, 480p, 360p) and format (MP4 / MP3)
- Real-time progress bar with download speed and ETA
- Cancel an active download
- Dark mode / Light mode with `localStorage` persistence
- Fully responsive — works on desktop, tablet, and mobile
- Security headers on every response
- In-process rate limiting (per IP)
- Concurrent download limit enforced
- Automatic cleanup of expired jobs and temporary files

---

## Tech Stack

| Layer      | Technology                     |
|------------|-------------------------------|
| Backend    | Python 3.11+, Flask            |
| Frontend   | HTML5, CSS3, Vanilla JavaScript |
| Downloader | yt-dlp                         |
| Media      | FFmpeg (external, required)    |
| WSGI       | Gunicorn                       |
| Deployment | Render (Docker-based)          |
| Testing    | pytest, pytest-flask           |

---

## Architecture

```
Browser
  │  POST /api/info           ← fetch metadata (no download)
  │  POST /api/download       ← create job, start background thread
  │  GET  /api/progress/<id>  ← poll every 1 s (JSON)
  │  POST /api/cancel/<id>    ← signal stop event
  │  GET  /download/<id>      ← serve completed file
  ▼
Flask (app.py)
  ├── utils.py        URL validation, filename sanitization, FFmpeg check
  ├── config.py       Environment variable configuration
  └── downloader.py   Downloader class + in-memory job manager
        └── yt-dlp → FFmpeg → output file in downloads/
```

Background downloads run in Python daemon threads.
Job state is stored in a module-level dict protected by `threading.Lock`.

---

## Project Structure

```
yt-downloader/
│
├── app.py                  Flask application + API routes
├── downloader.py           yt-dlp wrapper + job manager
├── config.py               Environment-variable configuration
├── utils.py                URL validation, sanitisation, FFmpeg check
│
├── templates/
│   ├── index.html          Main page
│   └── error.html          Error page (404, 500)
│
├── static/
│   ├── css/style.css       Responsive styling + dark mode
│   └── js/app.js           Frontend logic (fetch, poll, UI states)
│
├── downloads/              Temporary download directory (gitignored)
│   └── .gitkeep
│
├── tests/
│   ├── test_utils.py       Unit tests for utils
│   └── test_routes.py      Flask route tests (no real downloads)
│
├── Dockerfile              Docker image (Python 3.11 + FFmpeg)
├── Procfile                Gunicorn start command (non-Docker fallback)
├── render.yaml             Render deployment blueprint
├── requirements.txt        Production dependencies
├── requirements-dev.txt    Development/test dependencies
├── pytest.ini              pytest root-dir config (fixes imports)
├── .env.example            Example environment variables
├── .gitignore
├── LICENSE                 MIT
└── README.md
```

---

## Prerequisites

- **Python 3.11+**
- **FFmpeg** — required for MP4 merging and MP3 extraction

---

## Windows Installation

### 1. Clone or download the project

```cmd
cd yt-downloader
```

### 2. Create a virtual environment

```cmd
python -m venv venv
```

### 3. Activate the virtual environment

```cmd
venv\Scripts\activate
```

*(To deactivate later: `deactivate`)*

### 4. Install dependencies

```cmd
pip install -r requirements.txt
```

---

## FFmpeg Installation (Windows)

FFmpeg is required for:
- Merging separate video + audio tracks into a single MP4
- Converting audio to MP3

**Steps:**

1. Go to [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)  
   → Click "Windows" → choose a pre-built binary (e.g. from gyan.dev)
2. Extract the archive (e.g. to `C:\ffmpeg\`)
3. Add `C:\ffmpeg\bin` to your Windows **PATH** environment variable:
   - Open *System Properties → Advanced → Environment Variables*
   - Edit `Path` under *User variables* → Add `C:\ffmpeg\bin`
4. Open a **new** Command Prompt and verify:

```cmd
ffmpeg -version
```

You should see version information.

> **Note:** If FFmpeg is missing, the app will still start.  
> It will show a warning banner and video-only or audio-only  
> downloads may fail with a message explaining the issue.

---

## Running Locally (Development)

```cmd
python app.py
```

Open your browser at: [http://127.0.0.1:5000](http://127.0.0.1:5000)

Alternatively, using Flask's built-in server:

```cmd
flask --app app run --debug
```

---

## Running Tests

From the project root (virtual environment active):

```cmd
pytest -v
```

No `PYTHONPATH` setting required — `pytest.ini` handles this automatically.

Tests do **not** make real network requests or YouTube downloads.

---

## Production Server

To run with Gunicorn locally (Linux/macOS):

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app
```

Do **not** use `flask run` or `debug=True` in production.

---

## Render Deployment

This project deploys to [Render](https://render.com) using Docker,
which guarantees FFmpeg is available.

### Steps

1. **Create a GitHub repository** and push this project.
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repository.
4. Render will detect `render.yaml` automatically and configure:
   - **Environment:** Docker
   - **Dockerfile:** `./Dockerfile`
   - **Start command:** `gunicorn --bind 0.0.0.0:10000 ...`
5. Add environment variables in the Render dashboard (optional):
   - `SECRET_KEY` — auto-generated by render.yaml
   - `MAX_CONCURRENT_DOWNLOADS` — default: 3
   - `JOB_EXPIRATION` — default: 3600
6. Click **Deploy**.
7. Open the generated `.onrender.com` URL.
8. Paste a supported URL and test the download flow.

> **Cloud storage note:** Render's free tier uses an ephemeral filesystem.  
> Downloaded files are stored temporarily and will be lost on instance restart.  
> This is by design — YT Downloader is not a permanent file storage service.

---

## Environment Variables

| Variable                   | Default                          | Description                              |
|----------------------------|----------------------------------|------------------------------------------|
| `SECRET_KEY`               | `dev-secret-key-...`             | Flask session secret (change in prod)    |
| `DOWNLOAD_DIR`             | `downloads`                      | Temporary download directory             |
| `MAX_CONCURRENT_DOWNLOADS` | `5`                              | Max simultaneous downloads               |
| `JOB_EXPIRATION`           | `3600`                           | Seconds before old jobs are cleaned up   |
| `FLASK_ENV`                | `development`                    | `production` or `development`            |
| `MAX_REQUESTS_PER_MINUTE`  | `10`                             | Rate limit per IP (in-process only)      |

Copy `.env.example` to `.env` and edit values. Never commit `.env`.

---

## Security

- **Backend URL validation** — all requests validated server-side; frontend JS is not trusted
- **Format whitelist** — only `best` and `audio_only` accepted in download API
- **Path traversal protection** — `werkzeug.safe_join` used for all file serving
- **No user-controlled paths** — output filenames are generated server-side with job ID
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `CSP`
- **Rate limiting** — in-process per-IP rate limiter (not Redis-backed)
- **No shell injection** — yt-dlp Python API used directly; `shell=True` never used
- **No secrets in responses** — error messages never include stack traces or filesystem paths

---

## Responsible Use

This is an **educational project**.

- Only download content you own or have explicit permission to download.
- Respect copyright law and platform Terms of Service.
- This application does **not** implement DRM bypass, paywall bypass, or credential harvesting.
- Private, restricted, or unavailable videos are rejected with a clear error message.

---

## Known Limitations

1. **In-memory state** — job progress is lost if the server restarts.
2. **Ephemeral files** — downloaded files are stored in a local `downloads/` directory that is wiped on restart on most cloud platforms.
3. **Single-process rate limiter** — the built-in rate limiter does not work across multiple Gunicorn workers; for production use, add a reverse proxy rate limiter (e.g., Nginx).
4. **No persistent storage** — not suitable as a permanent file archive.
5. **FFmpeg required** — MP3 conversion and high-quality MP4 merging require FFmpeg.
6. **No real YouTube download tested automatically** — unit tests mock all external calls.

---

## Future Improvements

- Playlist support (multiple sequential downloads)
- Download queue with priority ordering
- Subtitle download support
- S3-compatible object storage for completed files (removes ephemeral limitation)
- Redis + Celery/RQ for a proper distributed job queue
- User authentication for personal download history
- Persistent download history (SQLite / PostgreSQL)
- Progress via Server-Sent Events instead of polling
- Admin dashboard for monitoring active jobs

---

## License

MIT License — see [LICENSE](LICENSE)
